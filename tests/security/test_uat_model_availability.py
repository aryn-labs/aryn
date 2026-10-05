"""Model discovery/rejection checks use HTTP transports only, never paid/live inference."""

import httpx
import pytest
from sqlalchemy import text

from modules.bench.runner import BenchRunner
from modules.core.workflows.coordinator import RunCoordinator
from packages.contracts.runtime import ModelUnavailableError, RunRequest, RuntimeModelAvailability
from packages.runtime_adapters import HermesRuntimeAdapter

MODEL = "stealth/space-bunny-alpha"


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory,status", [
    ({"provider": "nous", "providers": [{"slug": "nous", "authenticated": True, "models": [], "source": "hermes"}]}, "unavailable"),
    ({"provider": "nous", "providers": [{"slug": "nous", "authenticated": True, "models": [MODEL], "unavailable_models": [MODEL]}]}, "unavailable"),
    ({"provider": "nous", "providers": [{"slug": "nous", "authenticated": True, "models": [MODEL], "source": "hermes"}]}, "unknown"),
    ({"provider": "nous", "providers": [{"slug": "nous", "authenticated": False, "models": [MODEL]}]}, "unavailable"),
    ({"provider": "other-provider", "providers": []}, "unknown"),
    ({"providers": "malformed"}, "unknown"),
    (None, "unknown"),
])
async def test_discovery_never_treats_static_or_alias_catalog_as_availability(inventory, status):
    posts = []
    def transport(request):
        if request.method == "POST":
            posts.append(request)
        if request.url.path == "/api/model/options":
            return httpx.Response(200, json=inventory) if inventory is not None else httpx.Response(404)
        # Router alias listing is explicitly insufficient, even if it contains our exact model.
        return httpx.Response(200, json={"data": [{"id": MODEL}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = HermesRuntimeAdapter(api_key="isolated-test-only", http_client=client)
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
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={"data": []})
        requests.append(request)
        return httpx.Response(404, json={"error": {"code": "model_not_found", "message": "model missing; sensitive body must not escape"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = HermesRuntimeAdapter(api_key="isolated-test-only", http_client=client)
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
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={"data": []})
        posts.append(request)
        return httpx.Response(404, json={"error": {"code": "model_not_found"}})
    class DiscoveryRaceDouble(HermesRuntimeAdapter):
        async def model_availability(self, model, *, refresh=False):
            if model in self._rejected_models:
                return await super().model_availability(model, refresh=refresh)
            return RuntimeModelAvailability(model=model, status="available", source="isolated-discovery-race")
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = DiscoveryRaceDouble(api_key="isolated-test-only", http_client=client)
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
