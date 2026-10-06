import json
import httpx
import pytest

from packages.model_adapters.gateway import GatewaySettings, NineRouterGateway
from packages.contracts.runtime import GatewayUnavailableError, ModelUnavailableError
from tests.gateway_fixtures import MODEL, make_adapter, standard_handler


@pytest.mark.asyncio
async def test_discovery_success_is_sanitized():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: standard_handler(r, models=[
        {"id": MODEL, "availability": "available", "api_key": "MUST-NOT-LEAK", "display_name": "MUST-NOT-LEAK"}]))) as client:
        adapter = make_adapter(client)
        snapshot = await adapter.discover_models()
        assert snapshot.connected and snapshot.discovery_valid
        assert snapshot.models[0]["gateway"] == "9Router"
        assert "MUST-NOT-LEAK" not in snapshot.model_dump_json()
        await adapter.require_model_available(MODEL)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,expected", [
    ({"object": "list", "data": [{"id": MODEL}]}, "unknown"),
    ({"object": "list", "data": []}, "unavailable"),
    ({"object": "list", "data": [{"id": MODEL, "availability": "unavailable"}]}, "unavailable"),
    ({"object": "list", "data": [{"id": MODEL, "availability": "available", "owned_by": "combo"}]}, "unavailable"),
    ({"object": "list", "data": [{"id": MODEL}, {"id": MODEL}]}, "unknown"),
    ({"data": []}, "unknown"),
])
async def test_catalog_only_unknown_missing_unavailable_or_combo_blocks_dispatch(payload, expected):
    posts = []
    def handler(request):
        if request.method == "POST":
            posts.append(request)
        return httpx.Response(200, json=payload) if request.url.port == 20128 else standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client)
        assert (await adapter.model_availability(MODEL)).status == expected
        with pytest.raises((ModelUnavailableError, GatewayUnavailableError)):
            await adapter.require_model_available(MODEL)
    assert posts == []


@pytest.mark.asyncio
async def test_gateway_failure_discards_previous_catalog():
    offline = False
    def handler(request):
        if offline:
            raise httpx.ConnectError("sensitive error text", request=request)
        return standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client)
        assert (await adapter.discover_models()).models
        offline = True
        snapshot = await adapter.discover_models(refresh=True)
        assert snapshot.models == [] and not snapshot.discovery_valid and not snapshot.connected
        with pytest.raises(GatewayUnavailableError):
            await adapter.require_model_available(MODEL)
        assert "sensitive" not in snapshot.model_dump_json()


@pytest.mark.parametrize("url", ["https://provider.example/v1", "http://secret@127.0.0.1:20128/v1", "http://127.0.0.1:20128/v1?token=secret"])
def test_gateway_endpoint_cannot_embed_credentials_or_target_provider(url):
    with pytest.raises(ValueError):
        GatewaySettings(base_url=url)


def test_env_configuration_reads_only_centralized_allowlisted_variables(monkeypatch):
    import os
    reads = []
    original = os.getenv
    def read(name, *args):
        reads.append(name)
        assert name in {"ARYN_ENV", "ARYN_STUDIO_HOST", "ARYN_STUDIO_PORT", "ARYN_RUNTIME_BASE_URL",
                        "ARYN_9ROUTER_BASE_URL", "ARYN_9ROUTER_API_KEY", "API_SERVER_KEY"}
        return original(name, *args)
    monkeypatch.setattr(os, "getenv", read)
    settings = GatewaySettings.from_env()
    assert len(reads) == 7
    assert settings.base_url.endswith("/v1")


@pytest.mark.asyncio
@pytest.mark.parametrize("verified,source,age,expected", [
    (False, "provider_discovery", 0, "unknown"),
    (True, "internal_provider_state", 0, "unknown"),
    (True, "provider_discovery", 120, "unknown"),
    (True, "runtime_probe", -120, "unknown"),
    (True, "provider_discovery", 0, "available"),
])
async def test_only_fresh_public_availability_evidence_is_authoritative(monkeypatch, verified, source, age, expected):
    import time
    def forbid_database(*args, **kwargs):
        pytest.fail("Discovery must never consult the internal 9Router database")
    monkeypatch.setattr("sqlite3.connect", forbid_database)
    payload = {"object": "list", "data": [{"id": "cx/model-a", "owned_by": "codex",
        "availability": "available", "availability_verified": verified,
        "availability_source": source, "availability_checked_at": time.time() - age}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        gateway = NineRouterGateway(http_client=client)
        assert (await gateway.availability("cx/model-a")).status == expected
