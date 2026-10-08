"""Isolated installed-Hermes integration probe. Every SDK model call is a HTTP double."""
import asyncio
import json
import os
from pathlib import Path
import sys
import socket
import traceback

network_attempts = []
native_connect = socket.socket.connect

def reject_network(*args, **kwargs):
    caller = traceback.extract_stack(limit=2)[0]
    if caller.name == "_fallback_socketpair" and Path(caller.filename) == Path(socket.__file__):
        return native_connect(*args, **kwargs)
    network_attempts.append(True)
    raise RuntimeError("Network access forbidden in isolated Hermes integration test")

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

def metadata_double(self, request):
    # Native Hermes probes metadata independently of its model SDK. Return an
    # honest unsupported response without reaching any installed gateway.
    if request.method == "GET" or (request.method == "POST" and request.url.path == "/api/show"):
        return httpx.Response(404, request=request, json={"error": "isolated metadata unavailable"})
    network_attempts.append(("non-SDK model request", request.method, request.url.path))
    raise RuntimeError("Model requests must use the guarded SDK double")

httpx.HTTPTransport.handle_request = metadata_double
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
            "model_options": {"temperature": 0.2, "max_tokens": 128}}
    if asynchronous:
        body["input"] = "Isolated async test response " + model
    else:
        body["messages"] = [{"role": "user", "content": "Isolated test response " + model}]
    result._read_bytes = json.dumps(body).encode()
    return result


async def check():
    # Install after asyncio creates its internal Windows socketpair. No service
    # sockets may be opened while native Hermes handles the isolated turns.
    socket.socket.connect = reject_network
    socket.socket.connect_ex = reject_network
    print("PHASE_BUILD", flush=True)
    api = binding.build_adapter(settings, os.environ["API_SERVER_KEY"], port=0)
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
    assert network_attempts == [], "Native Hermes attempted a request outside the HTTP doubles"
    # Start the real wrapper listener, then resolve/dispatch its actual aiohttp
    # app. Only loopback bind is opened; model sockets remain forbidden.
    from aiohttp.test_utils import make_mocked_request
    from gateway.platforms.api_server import APIServerAdapter
    assert await api.connect()
    application = api._app
    assert all(sock.getsockname()[0] == "127.0.0.1" for sock in api._site._server.sockets)

    async def dispatch(method, path, body=None, authenticated=True, extra_headers=None):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + os.environ["API_SERVER_KEY"]
        headers.update(extra_headers or {})
        req = make_mocked_request(method, path, headers=headers, app=application)
        req._read_bytes = json.dumps(body or {}).encode()
        match = await application.router.resolve(req)
        req._match_info = match
        async def handler(incoming):
            return await match.handler(incoming)
        return await application.middlewares[0](req, handler)

    allowed = {(method, path) for method, path, _ in api._http_route_table()}
    for method, path, _ in APIServerAdapter._http_route_table(api):
        if (method, path) in allowed:
            continue
        path = path.replace("{session_id}", "s").replace("{job_id}", "j").replace("{platform}", "p").replace("{artifact_id}", "a").replace("{run_id}", runtime_id).replace("{response_id}", "r")
        assert (await dispatch(method, path)).status == 404, (method, path)
    for method, path in [("POST", "/api/cron/fire"), ("POST", "/p/other/api/jobs"),
                         ("GET", "/v1/browser-control/ws"), ("GET", "/unknown"),
                         ("POST", "/v1/runs/any/approval"), ("POST", "/v1/runs/any/steer")]:
        assert (await dispatch(method, path)).status == 404
    assert (await dispatch("GET", "/v1/toolsets", authenticated=False)).status == 401
    assert (await dispatch("GET", "/v1/toolsets")).status == 200
    assert (await dispatch("GET", "/v1/capabilities")).status == 200
    for extra in [{"tools": [{"type": "function"}]}, {"tool_choice": "auto"},
                  {"provider": "openai"}, {"fallback_model": "other/model"},
                  {"model_options": {"_aryn_receipt": {}}}, {"stream": True},
                  {"model_options": {"max_tokens": 64}}]:
        body = json.loads(request()._read_bytes)
        body.update(extra)
        assert (await dispatch("POST", "/v1/chat/completions", body)).status == 422
    ambiguous = json.loads(request(asynchronous=True)._read_bytes)
    ambiguous["max_tokens"] = 64
    assert (await dispatch("POST", "/v1/runs", ambiguous)).status == 422
    assert len(calls) == 6
    body = json.loads(request("test/model-http")._read_bytes)
    response = await dispatch("POST", "/v1/chat/completions", body)
    assert response.status == 200, response.body
    assert json.loads(response.body)["aryn"]["actual_model"] == "test/model-http"
    assert len(calls) == 7
    assert (await dispatch("POST", "/v1/chat/completions", body, extra_headers={"X-Hermes-Session-Id": "foreign"})).status == 403
    assert (await dispatch("POST", "/v1/chat/completions", body, extra_headers={"X-Hermes-Session-Key": "foreign"})).status == 403
    assert (await dispatch("GET", "/v1/capabilities", extra_headers={"Upgrade": "websocket"})).status == 403
    assert (await dispatch("GET", "/v1/runs/" + runtime_id)).status == 200
    import logging
    logging.getLogger("runtime.security.probe").warning("credential %s gateway %s", os.environ["API_SERVER_KEY"], settings.api_key.get_secret_value())
    await api.disconnect()
    await restarted_api.disconnect()
    print("REAL_HERMES_CONFINED_ROUTES_PASS")
    print("REAL_HERMES_ISOLATED_GATEWAY_PASS")

try:
    asyncio.run(check())
except BaseException:
    traceback.print_exc()
    sys.exit(1)
