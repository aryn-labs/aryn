"""Model discovery/rejection checks use HTTP transports only, never paid/live inference."""

import httpx
import pytest
from sqlalchemy import text

from modules.bench.runner import BenchRunner
from modules.core.workflows.coordinator import RunCoordinator
from packages.contracts.runtime import ModelUnavailableError, RunRequest, RuntimeModelAvailability

from tests.gateway_fixtures import MODEL, make_adapter, standard_handler


@pytest.mark.asyncio
async def test_multi_provider_catalog_labels_and_statuses_never_authorize_execution():
    import time
    rows = [
        {"id": "ds/deepseek-flash", "provider": "fixture-provider-a", "provider_configured": True},
        {"id": "ag/gemini-2.5-pro", "provider": "fixture-provider-b", "provider_configured": True,
            "provider_reachability": "reachable", "provider_reachability_verified": True,
            "provider_reachability_source": "provider_discovery", "provider_reachability_checked_at": time.time()},
        {"id": "cx/gpt-6-sol", "availability": "unavailable", "provider_configured": False},
        {"id": "unknown/Model-A"},
    ]
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"object": "list", "data": rows})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client)
        catalog = await adapter.discover_models(refresh=True)
        assert catalog.discovery_valid
        assert [r["model_id"] for r in catalog.models] == [r["id"] for r in rows]
        assert [r["display_name"] for r in catalog.models] == ["DeepSeek Flash", "Gemini 2.5 Pro", "GPT 6 Sol", "unknown/Model-A"]
        first, second, third, fourth = catalog.models
        assert first["provider"] == "fixture-provider-a" and second["provider"] == "fixture-provider-b"
        assert first["provider_configured"] == "configured" and first["provider_reachability"] == "unknown"
        assert second["provider_reachability"] == "reachable" and second["availability"] == "unknown"
        assert third["availability"] == "unavailable" and third["provider_configured"] == "unconfigured"
        assert fourth["provider_identity_status"] == fourth["provider_configured"] == "unknown"
        assert all(r["listed"] and r["credit_status"] == r["rate_limit_status"] == "unknown" for r in catalog.models)
        for row in rows:
            assert (await adapter.model_capabilities(row["id"])).tool_calling == "unknown"
        assert (await adapter.model_availability("absent/model", refresh=True)).status == "unavailable"
    assert all(request.method == "GET" for request in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["duplicate", "invalid", "http", "malformed", "secret_label", "secret_provider"])
async def test_discovery_failure_discards_snapshot_and_untrusted_metadata(fault):
    state = {"fault": False}
    secret = "isolated-sensitive-value"
    def handler(request):
        if not state["fault"]:
            return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})
        rows = [{"id": MODEL}]
        if fault == "duplicate":
            rows *= 2
        elif fault == "invalid":
            rows = [{"id": "not a model identity"}]
        elif fault.startswith("secret_"):
            rows[0]["display_name" if fault == "secret_label" else "provider"] = secret
        return httpx.Response(503 if fault == "http" else 200,
            json={} if fault == "malformed" else {"object": "list", "data": rows})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client, secret=secret)
        assert (await adapter.discover_models(refresh=True)).discovery_valid
        state["fault"] = True
        result = await adapter.discover_models(refresh=True)
        assert not result.discovery_valid and result.models == []
        assert secret not in result.model_dump_json()


@pytest.mark.parametrize("mid,metadata,label", [
    ("ds/deepseek-flash", {}, "DeepSeek Flash"),
    ("ag/gemini-2.5-flash", {}, "Gemini 2.5 Flash"),
    ("ag/gemini-2.5-pro", {}, "Gemini 2.5 Pro"),
    ("owner/model-name", {}, "owner/model-name"),
    ("ag/owner/model-name", {}, "ag/owner/model-name"),
    ("Model-X.2", {}, "Model X.2"),
    ("gpt-4.1", {}, "GPT 4.1"),
    ("vendor/model", {"name": "Catalog Model 1.2"}, "Catalog Model 1.2"),
    ("vendor/model", {"name": "<script>secret</script>"}, "vendor/model"),
])
def test_model_label_is_presentation_only_and_conservative(mid, metadata, label):
    from packages.model_adapters.gateway import model_display_name
    row = {"id": mid, **metadata}
    assert model_display_name(row) == label
    assert row == {"id": mid, **metadata}


@pytest.mark.asyncio
async def test_duplicate_labels_are_distinct_without_changing_ids_or_provider_claims():
    rows = [{"id": "ds/model-a", "name": "Shared Model"}, {"id": "ag/model-b", "name": "shared model"}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,
            json={"object": "list", "data": rows}))) as client:
        snapshot = await make_adapter(client).discover_models(refresh=True)
    assert [r["model_id"] for r in snapshot.models] == ["ds/model-a", "ag/model-b"]
    assert [r["display_name"] for r in snapshot.models] == ["Shared Model [ds/model-a]", "shared model [ag/model-b]"]
    assert all(r["provider_identity_status"] == "unknown" for r in snapshot.models)


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory,status", [
    ({"object": "list", "data": []}, "unavailable"),
    ({"object": "list", "data": [{"id": MODEL, "availability": "unavailable"}]}, "unavailable"),
    ({"object": "list", "data": [{"id": MODEL}]}, "unknown"),
    ({"object": "list", "data": [{"id": MODEL, "owned_by": "combo"}]}, "unavailable"),
])
async def test_discovery_never_treats_static_or_alias_catalog_as_availability(inventory, status):
    posts = []
    def transport(request):
        if request.method == "POST":
            posts.append(request)
        if request.url.port == 20128:
            return httpx.Response(200, json=inventory)
        return standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = make_adapter(client)
        result = await adapter.model_availability(MODEL)
        assert result.status == status and result.model == MODEL
        with pytest.raises(ModelUnavailableError):
            await adapter.require_model_available(MODEL)
    assert posts == []


@pytest.mark.asyncio
async def test_provider_rejection_is_sanitized_and_sticky_without_silent_fallback(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    requests = []
    def transport(request):
        if request.url.port == 20128 or request.url.path in {"/v1/toolsets", "/aryn/gateway"}:
            return standard_handler(request)
        requests.append(request)
        return httpx.Response(404, json={"error": {"code": "model_not_found", "message": "model missing; sensitive body must not escape"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = make_adapter(client)
        with pytest.raises(ModelUnavailableError) as error:
            await adapter.execute_direct_turn(RunRequest(prompt="Test", model=MODEL), ctx)
        assert "sensitive" not in str(error.value)
        assert (await adapter.model_availability(MODEL, refresh=True)).status == "unavailable"
        with pytest.raises(ModelUnavailableError):
            await adapter.require_model_available(MODEL)
    assert len(requests) == 1
    assert requests[0].read().decode().find(MODEL) != -1


@pytest.mark.asyncio
async def test_model_disappearing_after_preflight_stops_bench_after_one_rejection(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    previous = await factory.evaluate_version_with_bench(ctx, version.id)
    posts = []
    def transport(request):
        if request.url.port == 20128 or request.url.path in {"/v1/toolsets", "/aryn/gateway"}:
            return standard_handler(request, models=[{"id": version.model, "availability": "available"}])
        posts.append(request)
        return httpx.Response(404, json={"error": {"code": "model_not_found"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = make_adapter(client)
        factory.bench_runner = BenchRunner(adapter)
        with pytest.raises(ModelUnavailableError):
            await factory.evaluate_version_with_bench(ctx, version.id)
        with pytest.raises(ModelUnavailableError):
            await factory.evaluate_version_with_bench(ctx, version.id)
    assert len(posts) == 1  # The other three scenarios and retry never dispatch.
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM bench_evaluations")).scalar() == 1
        assert session.execute(text("SELECT id FROM bench_evaluations")).scalar() == previous.evaluation_id
        assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["direct", "async"])
async def test_core_blocks_unknown_model_availability_before_dispatch(lifecycle, mode):
    db, ctx, runtime, factory, bp, version = lifecycle
    async def unknown(model, **kwargs):
        return RuntimeModelAvailability(model=model)
    runtime.model_availability = unknown
    dispatches = []
    async def unexpected_dispatch(request, context):
        dispatches.append(request.model)
        raise AssertionError("Unknown availability must not dispatch")
    runtime.execute_direct_turn = unexpected_dispatch
    runtime.start_run = unexpected_dispatch
    coordinator = RunCoordinator(runtime, db_manager=db)
    request = RunRequest(prompt="Test", model="mock-fast", idempotency_key=f"unknown-{mode}")
    with pytest.raises(ModelUnavailableError):
        if mode == "direct":
            await coordinator.execute_managed_direct_turn(request, ctx)
        else:
            await coordinator.start_managed_run(request, ctx)
    assert runtime.requests == []
    assert dispatches == []
