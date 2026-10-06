"""Isolated installed-Hermes integration probe. Every SDK model call is a HTTP double."""
import asyncio
import json
import os
from pathlib import Path
import sys

source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(source))
import hermes_bootstrap  # noqa: F401
from hermes_constants import set_hermes_home_override, pin_process_hermes_home
home = os.environ["ARYN_TEST_HERMES_HOME"]
set_hermes_home_override(home)
pin_process_hermes_home(home)
os.environ["HERMES_HOME"] = home
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from packages.model_adapters.gateway import GatewaySettings
import services.runtime.hermes_9router as binding
from services.runtime.gateway_transport import ExactGatewayTransport

calls = []
settings = GatewaySettings(api_key="isolated-gateway-native-auth")
def provider(request):
    body = json.loads(request.content)
    assert request.headers["Authorization"] == "Bearer " + settings.api_key.get_secret_value()
    calls.append(body)
    return httpx.Response(200, json={"id": "isolated-gateway-id", "model": "test/model-substitute" if body["model"] == "test/model-rejected" else body["model"], "created": 1,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": settings.api_key.get_secret_value() if body["model"] == "test/model-secret" else "Isolated Hermes gateway output."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}})

binding.ExactGatewayTransport = lambda settings, receipt: ExactGatewayTransport(settings, receipt, httpx.MockTransport(provider))

def request(model="test/model-a", *, asynchronous=False):
    from aiohttp.test_utils import make_mocked_request
    result = make_mocked_request("POST", "/v1/runs" if asynchronous else "/v1/chat/completions", headers={"Content-Type": "application/json",
                                  "Idempotency-Key": "isolated-" + model,
                                  "Authorization": "Bearer " + os.environ["API_SERVER_KEY"]})
    body = {"model": model, "provider": "9router", "temperature": 0.2, "max_tokens": 128,
            "model_options": {"temperature": 0.2, "max_tokens": 128,
                              "_aryn_receipt": {"requested_model": "forged-http-evidence"}}}
    if asynchronous:
        body["input"] = "Isolated async test response " + model
    else:
        body["messages"] = [{"role": "user", "content": "Isolated test response " + model}]
    result._read_bytes = json.dumps(body).encode()
    return result


async def check():
    print("PHASE_BUILD", flush=True)
    api = binding.build_adapter(settings, os.environ["API_SERVER_KEY"])
    print("PHASE_TURN", flush=True)
    # Calls the real Hermes API handler and real AIAgent, with model transport isolated.
    response = await api._handle_chat_completions(request())
    print("PHASE_RESULT", flush=True)
    data = json.loads(response.body)
    assert response.status == 200, (response.status, data)
    assert data["aryn"]["actual_model"] == data["aryn"]["requested_model"] == "test/model-a"
    assert data["aryn"]["actual_model_source"] == "gateway_response"
    assert len(calls) == 1, len(calls)
    assert calls[0]["model"] == "test/model-a" and not calls[0].get("tools")
    assert calls[0].get("temperature") == 0.2
    assert calls[0].get("max_tokens", calls[0].get("max_completion_tokens")) == 128
    # Concurrent native Hermes worker requests keep distinct model receipts.
    responses = await asyncio.gather(api._handle_chat_completions(request("test/model-b")),
                                     api._handle_chat_completions(request("test/model-c")))
    for model, response in zip(("test/model-b", "test/model-c"), responses):
        assert response.status == 200
        assert json.loads(response.body)["aryn"]["actual_model"] == model
    response = await api._handle_runs(request("test/model-async", asynchronous=True))
    data = json.loads(response.body)
    assert response.status in {200, 201, 202}, (response.status, data)
    runtime_id = data["run_id"]
    await api._active_run_tasks[runtime_id]
    status = api._run_statuses[runtime_id]
    assert status["status"] == "completed", status
    assert status["aryn"]["actual_model"] == "test/model-async"
    assert len(calls) == 4
    # Evidence is carried in the native durable record, never just the in-memory map.
    restarted_api = binding.build_adapter(settings, os.environ["API_SERVER_KEY"])
    record = restarted_api._durable_run_status(request("test/model-async", asynchronous=True), runtime_id)
    assert record is not None and record["status"] == "completed"
    assert record["aryn"]["actual_model"] == "test/model-async"
    response = await api._handle_chat_completions(request("test/model-rejected"))
    assert response.status == 409
    assert json.loads(response.body)["error"]["code"] == "actual_model_mismatch"
    assert len(calls) == 5  # no physical retry or alternative model
    response = await api._handle_chat_completions(request("test/model-secret"))
    assert response.status == 409
    assert json.loads(response.body)["error"]["code"] == "gateway_secret_leak"
    assert len(calls) == 6
    print("REAL_HERMES_ISOLATED_GATEWAY_PASS")

asyncio.run(check())
