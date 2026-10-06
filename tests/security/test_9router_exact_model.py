import copy
import json

import httpx
import pytest

from packages.contracts.runtime import RunRequest, ModelIdentityError, RuntimeGatewayError
from packages.runtime_adapters import HermesAdapterError
from packages.model_adapters.gateway import GatewaySettings
from services.runtime.gateway_transport import ExactGatewayTransport, ModelReceipt
from tests.gateway_fixtures import MODEL, COMPLETION, make_adapter, standard_handler


@pytest.mark.asyncio
@pytest.mark.parametrize("change,error", [(None, None), ("mismatch", ModelIdentityError), ("echo_only", RuntimeGatewayError)])
async def test_hermes_response_must_prove_actual_gateway_model(lifecycle, change, error):
    _, ctx, *_ = lifecycle
    response = copy.deepcopy(COMPLETION)
    if change == "mismatch":
        response["aryn"]["actual_model"] = "test/model-b"
    if change == "echo_only":
        response.pop("aryn")
    posts = []
    def handler(request):
        if request.method == "POST":
            posts.append(json.loads(request.content))
        return standard_handler(request, response=response)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client)
        if error:
            with pytest.raises(error):
                await adapter.execute_direct_turn(RunRequest(prompt="Isolated test", model=MODEL), ctx)
        else:
            result = await adapter.execute_direct_turn(RunRequest(prompt="Isolated test", model=MODEL), ctx)
            assert result.requested_model == result.actual_model == MODEL
            assert result.gateway == "9Router" and result.runtime_backend == "Hermes"
            assert result.raw_response == {}
    assert len(posts) == 1 and posts[0]["provider"] == "9router" and posts[0]["model"] == MODEL


@pytest.mark.parametrize("actual", [MODEL, "test/model-b", None])
def test_runtime_sdk_transport_enforces_exact_model_and_latches_rejection(actual):
    calls = []
    def gateway(request):
        calls.append(request)
        response = copy.deepcopy(COMPLETION)
        response["model"] = actual
        response["api_key"] = "UNTRUSTED-PROVIDER-KEY"
        return httpx.Response(200, json=response)
    receipt = ModelReceipt(MODEL)
    transport = ExactGatewayTransport(GatewaySettings(), receipt, httpx.MockTransport(gateway))
    with httpx.Client(transport=transport) as client:
        result = client.post("http://127.0.0.1:20128/v1/chat/completions", json={"model": MODEL}, headers={"Authorization": "Bearer forbidden-provider-key"})
        assert "UNTRUSTED-PROVIDER-KEY" not in result.text
        if actual == MODEL:
            assert result.status_code == 200 and receipt.evidence()["actual_model"] == MODEL
        else:
            assert result.status_code == 400 and receipt.evidence() is None
            assert client.post("http://127.0.0.1:20128/v1/chat/completions", json={"model": MODEL}).status_code == 400
    assert len(calls) == 1
    assert "Authorization" not in calls[0].headers


def test_sdk_never_dispatches_alternate_gateway_or_model():
    calls = []
    for url, model in [("https://provider.example/v1/chat/completions", MODEL), ("http://127.0.0.1:20128/v1/chat/completions", "test/model-b")]:
        receipt = ModelReceipt(MODEL)
        with httpx.Client(transport=ExactGatewayTransport(GatewaySettings(), receipt,
                         httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200)))) as client:
            assert client.post(url, json={"model": model}).status_code == 400
    assert calls == []


@pytest.mark.asyncio
async def test_gateway_secret_does_not_leak_in_response_errors_or_logs(lifecycle, caplog):
    _, ctx, *_ = lifecycle
    secret = "isolated-gateway-secret-value"
    def handler(request):
        if request.method == "POST":
            return httpx.Response(500, json={"error": {"message": secret}})
        return standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client, secret=secret)
        with pytest.raises(HermesAdapterError) as exc:
            await adapter.execute_direct_turn(RunRequest(prompt="Isolated test", model=MODEL), ctx)
        assert secret not in str(exc.value)
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_runtime_binding_missing_prevents_any_inference(lifecycle):
    _, ctx, *_ = lifecycle
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path == "/aryn/gateway":
            return httpx.Response(404)
        return standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeGatewayError):
            await make_adapter(client).execute_direct_turn(RunRequest(prompt="Test", model=MODEL), ctx)
    assert all(r.method == "GET" for r in calls)


@pytest.mark.parametrize("location", ["health", "result", "discovery", "async_start"])
@pytest.mark.asyncio
async def test_raw_runtime_secret_is_never_returned(lifecycle, location, caplog):
    _, ctx, *_ = lifecycle
    secret = "isolated-gateway-sensitive-value"
    def handler(request):
        if location == "health" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": secret})
        if location == "discovery" and request.url.port == 20128:
            return httpx.Response(200, json={"object": "list", "data": [{"id": secret}]})
        if location == "result" and request.method == "POST":
            response = copy.deepcopy(COMPLETION)
            response["choices"][0]["message"]["content"] = secret
            return httpx.Response(200, json=response)
        if location == "async_start" and request.url.path == "/v1/runs":
            return httpx.Response(202, json={"run_id": secret, "status": "queued"})
        return standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client, secret=secret)
        if location == "discovery":
            snapshot = await adapter.discover_models()
            assert not snapshot.discovery_valid and secret not in snapshot.model_dump_json()
        else:
            with pytest.raises(HermesAdapterError) as exc:
                if location == "health":
                    await adapter.health()
                elif location == "async_start":
                    await adapter.start_run(RunRequest(prompt="Isolated", model=MODEL), ctx)
                else:
                    await adapter.execute_direct_turn(RunRequest(prompt="Isolated", model=MODEL), ctx)
            assert secret not in str(exc.value)
    assert secret not in caplog.text
