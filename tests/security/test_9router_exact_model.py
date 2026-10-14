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


@pytest.mark.parametrize("actual,accepted", [("openai/gpt-4o-mini", True), ("gpt-4o-mini", False),
    ("gpt-4o-mini-2024-07-18", False), ("gpt-4o", False), ("other/gpt-4o-mini", False)])
def test_gateway_namespace_requires_exact_identity_without_alias_assumptions(actual, accepted):
    requested = "openai/gpt-4o-mini"
    response = copy.deepcopy(COMPLETION)
    response["model"] = actual
    receipt = ModelReceipt(requested)
    with httpx.Client(transport=ExactGatewayTransport(GatewaySettings(), receipt,
            httpx.MockTransport(lambda r: httpx.Response(200, json=response)))) as client:
        result = client.post("http://127.0.0.1:20128/v1/chat/completions", json={"model": requested})
    assert (result.status_code == 200) is accepted
    assert bool(receipt.evidence()) is accepted


@pytest.mark.parametrize("requested,reported", [("ds/deepseek-flash", "deepseek-flash"),
    ("ag/gemini-2.5-pro", "gemini-2.5-pro"), ("cx/gpt-6-sol", "openai/gpt-6-sol")])
def test_provider_aliases_cannot_change_signed_model_identity(requested, reported):
    receipt = ModelReceipt(requested)
    response = {**COMPLETION, "model": reported}
    with httpx.Client(transport=ExactGatewayTransport(GatewaySettings(), receipt,
            httpx.MockTransport(lambda r: httpx.Response(200, json=response)))) as client:
        assert client.post("http://127.0.0.1:20128/v1/chat/completions", json={"model": requested}).status_code == 400
    assert receipt.failure == "actual_model_mismatch" and receipt.evidence() is None


@pytest.mark.parametrize("status,code,expected", [(429, "rate_limit_exceeded", "provider_rate_limited"),
    (429, "insufficient_quota", "provider_quota_exhausted"), (402, "insufficient_balance", "provider_insufficient_credit"),
    (429, "insufficient_credit", "provider_insufficient_credit"),
    (503, "unknown", "provider_unavailable"), (400, "unknown", "gateway_rejected")])
def test_provider_errors_are_distinct_sanitized_and_never_retry(status, code, expected):
    from modules.core.errors import public_error
    from packages.contracts.runtime import ProviderRequestError
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": code, "message": "private provider response"}})
    receipt = ModelReceipt(MODEL)
    with httpx.Client(transport=ExactGatewayTransport(GatewaySettings(), receipt, httpx.MockTransport(handler))) as client:
        for _ in range(2):
            result = client.post("http://127.0.0.1:20128/v1/chat/completions", json={"model": MODEL})
            assert result.json()["error"]["code"] == expected
            assert "private" not in result.text
    assert len(calls) == 1 and receipt.evidence() is None
    if expected.startswith("provider_"):
        adapter = make_adapter(None)
        with pytest.raises(ProviderRequestError) as error:
            adapter._check_model_rejection(result, MODEL)
        assert public_error(error.value)["error_code"] == expected


def test_text_turn_native_history_is_private_to_actor_scope_and_request(lifecycle):
    _, ctx, *_ = lifecycle
    from packages.runtime_adapters import HermesRuntimeAdapter
    adapter = HermesRuntimeAdapter(api_key="isolated")
    request = RunRequest(model=MODEL, prompt="Identical text", idempotency_key="isolated-key")
    original = adapter._run_headers(request, ctx)["Idempotency-Key"]
    assert adapter._run_headers(request, ctx)["Idempotency-Key"] == original
    assert "X-Hermes-Session-Id" not in adapter._run_headers(request, ctx)
    variants = [ctx.model_copy(update={"organization_id": "other-org"}),
        ctx.model_copy(update={"project_id": "other-project"}),
        ctx.model_copy(update={"actor": ctx.actor.model_copy(update={"actor_id": "other-user"})})]
    assert all(adapter._run_headers(request, changed)["Idempotency-Key"] != original for changed in variants)
    assert adapter._run_headers(request.model_copy(update={"idempotency_key": "other-key"}), ctx)["Idempotency-Key"] != original
    assigned = adapter._run_headers(request.model_copy(update={"session_id": "assignment-owned"}), ctx)
    assert assigned["X-Hermes-Session-Key"] == "assignment-owned" and "X-Hermes-Session-Id" not in assigned


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


def test_gateway_output_cap_and_single_dispatch_even_after_success():
    calls = []
    def gateway(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=copy.deepcopy(COMPLETION))
    receipt = ModelReceipt(MODEL, transport={"max_tokens": 64})
    with httpx.Client(transport=ExactGatewayTransport(GatewaySettings(), receipt, httpx.MockTransport(gateway))) as client:
        body = {"model": MODEL, "max_tokens": 9999, "max_completion_tokens": 9999, "n": 5}
        assert client.post("http://127.0.0.1:20128/v1/chat/completions", json=body).status_code == 200
        assert client.post("http://127.0.0.1:20128/v1/chat/completions", json=body).status_code == 400
    assert calls == [{"model": MODEL, "max_tokens": 64, "stream": False}]
    assert receipt.failure == "additional_dispatch_forbidden" and receipt.evidence() is None


def test_concurrent_sdk_dispatches_share_receipt_latch():
    from concurrent.futures import ThreadPoolExecutor
    import threading
    entered, release = threading.Event(), threading.Event()
    calls = []
    def gateway(request):
        calls.append(request)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, json=copy.deepcopy(COMPLETION))
    receipt = ModelReceipt(MODEL, transport={"max_tokens": 64})
    with httpx.Client(transport=ExactGatewayTransport(GatewaySettings(), receipt, httpx.MockTransport(gateway))) as client:
        with ThreadPoolExecutor(2) as workers:
            first = workers.submit(client.post, "http://127.0.0.1:20128/v1/chat/completions", json={"model": MODEL})
            assert entered.wait(5)
            second = workers.submit(client.post, "http://127.0.0.1:20128/v1/chat/completions", json={"model": MODEL})
            try:
                assert second.result(timeout=5).status_code == 400
            finally:
                release.set()
            assert first.result(timeout=5).status_code == 200
    assert len(calls) == 1 and receipt.evidence() is None
