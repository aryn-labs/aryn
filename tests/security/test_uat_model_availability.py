"""Model discovery/rejection checks use HTTP transports only, never paid/live inference."""

import httpx
import pytest
from sqlalchemy import text

from modules.bench.runner import BenchRunner
from modules.core.workflows.coordinator import RunCoordinator
from packages.contracts.runtime import ModelUnavailableError, RunRequest, RuntimeModelAvailability
from packages.runtime_adapters import HermesRuntimeAdapter

from tests.gateway_fixtures import MODEL, make_adapter, standard_handler


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
