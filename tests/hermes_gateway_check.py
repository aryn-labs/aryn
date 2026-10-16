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
    if body["model"] in {"test/tool-model", "test/mcp-tool-model", "test/https-tool-model", "test/github-tool-model"}:
        from packages.tool_adapters.fixture import definition
        from packages.contracts.tool import ToolDeclaration
        declaration = ToolDeclaration(name="aryn_mcp_project_lookup", input_schema={"type": "object",
            "properties": {"key": {"enum": ["aryn-core"]}}, "required": ["key"], "additionalProperties": False})
        if body["model"] == "test/https-tool-model":
            from packages.contracts.tool import HTTPS_INPUT_SCHEMA
            declaration = ToolDeclaration(name="aryn_https_project_lookup", input_schema=HTTPS_INPUT_SCHEMA)
        if body["model"] == "test/github-tool-model":
            from packages.contracts.tool import GITHUB_ISSUE_TOOL, GITHUB_ISSUE_INPUT
            declaration = ToolDeclaration(name=GITHUB_ISSUE_TOOL, input_schema=GITHUB_ISSUE_INPUT)
        selected = declaration.definition() if body["model"] != "test/tool-model" else definition()
        assert body.get("tools") == [selected]
        continued = any(m.get("role") == "tool" for m in body["messages"])
        summary = "Synthetic issue 42: open" if body["model"] == "test/github-tool-model" else "ARYN Core owns execution authorization."
        arguments = '{"issue_number":42}' if body["model"] == "test/github-tool-model" else '{"key":"aryn-core"}'
        message = {"role": "assistant", "content": json.dumps({"summary": summary})} if continued else {
            "role": "assistant", "content": None, "tool_calls": [{"id": "native_fixture_call", "type": "function",
                "function": {"name": selected["function"]["name"], "arguments": arguments}}]}
        return httpx.Response(200, json={"id": "native-tool-step", "model": body["model"], "created": 1,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop" if continued else "tool_calls"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}})
    return httpx.Response(200, json={"id": "isolated-gateway-id", "model": "test/model-substitute" if body["model"] == "test/model-rejected" else body["model"], "created": 1,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": settings.api_key.get_secret_value() if body["model"] == "test/model-secret" else "Isolated Hermes gateway output."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}})

binding.ExactGatewayTransport = lambda settings, receipt: ExactGatewayTransport(settings, receipt, httpx.MockTransport(provider))

def request(model="test/model-a", *, asynchronous=False):
    from aiohttp.test_utils import make_mocked_request
    headers = {"Content-Type": "application/json", "Idempotency-Key": "isolated-" + model,
        "Authorization": "Bearer " + os.environ["API_SERVER_KEY"]}
    result = make_mocked_request("POST", "/v1/runs" if asynchronous else "/v1/chat/completions", headers=headers)
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
    native_sessions = []
    native_factory = api._create_agent
    def tracked_factory(**kwargs):
        native_sessions.append(kwargs.get("session_id"))
        return native_factory(**kwargs)
    api._create_agent = tracked_factory
    print("PHASE_TURN", flush=True)
    # Calls the real Hermes API handler and real AIAgent, with model transport isolated.
    response = await api._handle_chat_completions(request())
    print("PHASE_RESULT", flush=True)
    data = json.loads(response.body)
    assert response.status == 200, (response.status, data)
    assert data["aryn"]["actual_model"] == data["aryn"]["requested_model"] == "test/model-a"
    assert data["aryn"]["actual_model_source"] == "gateway_response"
    assert response.headers["X-Hermes-Session-Id"].startswith("aryn_")
    assert len(calls) == 1, len(calls)
    assert calls[0]["model"] == "test/model-a" and not calls[0].get("tools")
    assert calls[0].get("temperature") == 0.2
    assert calls[0].get("max_tokens", calls[0].get("max_completion_tokens")) == 128
    # Concurrent native Hermes worker requests keep distinct model receipts.
    responses = await asyncio.gather(api._handle_chat_completions(request("test/model-b")),
                                     api._handle_chat_completions(request("test/model-c")))
    for model, response in zip(("test/model-b", "test/model-c"), responses, strict=True):
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
    assert "X-Hermes-Session-Id" not in response.headers
    first_session = native_sessions[-1]
    second = await dispatch("POST", "/v1/chat/completions", body,
        extra_headers={"Idempotency-Key": "isolated-same-text-new-core-scope"})
    assert second.status == 200, second.body
    assert "X-Hermes-Session-Id" not in second.headers
    assert native_sessions[-1].startswith("aryn_")
    assert native_sessions[-1] != first_session
    assert len(calls) == 8
    assert (await dispatch("POST", "/v1/chat/completions", body, extra_headers={"X-Hermes-Session-Id": "foreign"})).status == 403
    assert (await dispatch("POST", "/v1/chat/completions", body, extra_headers={"X-Hermes-Session-Key": "foreign"})).status == 403
    assert (await dispatch("GET", "/v1/capabilities", extra_headers={"Upgrade": "websocket"})).status == 403
    assert (await dispatch("GET", "/v1/runs/" + runtime_id)).status == 200
    # Real AIAgent proposes, pauses at transport BEFORE native dispatch, then
    # consumes a locally schema-verified fixture result on a separate bounded turn.
    from packages.contracts.runtime import RunRequest, ToolTurnRequest, ToolTurnResult, ToolExecutionContext
    from packages.tool_adapters import fixture
    turn = ToolTurnRequest(run_id="core_fixture_run", organization_id="isolated-org", project_id="isolated-project",
        iteration=1, tool_names=[fixture.NAME], request=RunRequest(model="test/tool-model", max_tokens=128,
            prompt="Read aryn-core and summarize it.", metadata={"initial_prompt": "Read aryn-core and summarize it."}))
    assert (await dispatch("POST", "/aryn/turn", turn.model_dump(mode="json"), authenticated=False)).status == 401
    invalid = turn.model_dump(mode="json")
    invalid["tool_names"] = ["terminal"]
    assert (await dispatch("POST", "/aryn/turn", invalid)).status == 422
    assert len(calls) == 8
    response = await dispatch("POST", "/aryn/turn", turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    proposed = ToolTurnResult.model_validate_json(response.body)
    assert proposed.tool_calls[0].name == fixture.NAME and proposed.result.status.value == "running"
    assert proposed.result.usage.total_tokens == 11 and len(calls) == 9
    data = fixture.execute(proposed.tool_calls[0].arguments, ToolExecutionContext(run_id=turn.run_id,
        organization_id=turn.organization_id, project_id=turn.project_id, deadline_at=__import__("time").time() + 30,
        call_number=1))
    turn.iteration = 2
    turn.history = [{"role": "user", "content": turn.request.prompt},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "native_fixture_call", "type": "function",
            "function": {"name": fixture.NAME, "arguments": '{"key":"aryn-core"}'}}]},
        {"role": "tool", "name": fixture.NAME, "tool_call_id": "native_fixture_call", "content": json.dumps(data)}]
    turn.request.prompt = "Continue using the verified tool result."
    response = await dispatch("POST", "/aryn/turn", turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    final = ToolTurnResult.model_validate_json(response.body)
    assert final.result.status.value == "completed" and not final.tool_calls
    assert json.loads(final.result.output) == {"summary": data["text"]}
    assert final.result.usage.total_tokens == 11 and len(calls) == 10
    assert network_attempts == []
    print("REAL_HERMES_GOVERNED_PROPOSAL_CONTINUATION_PASS")
    # Explicit capability-probe mode uses the same native boundary; transport
    # doubles remain labeled and cannot become live capability evidence.
    from packages.contracts.model import tool_probe_request, TOOL_PROBE_PROMPT
    assert proposed.result.model_evidence.origin == "isolated_test_double"
    turn.request = tool_probe_request("test/tool-model", "isolated-native-probe")
    turn.request.metadata = {"initial_prompt": TOOL_PROBE_PROMPT}
    turn.verification_mode, turn.iteration, turn.history = "tool_calling", 1, []
    invalid = turn.model_dump(mode="json")
    invalid["request"]["prompt"] = "Non-probe request"
    assert (await dispatch("POST", "/aryn/turn", invalid)).status == 422
    assert len(calls) == 10
    response = await dispatch("POST", "/aryn/turn", turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    probe = ToolTurnResult.model_validate_json(response.body)
    assert probe.tool_calls[0].name == fixture.NAME
    turn.history = [{"role": "user", "content": TOOL_PROBE_PROMPT},
        {"role": "assistant", "content": "", "tool_calls": [{"id": probe.tool_calls[0].call_id, "type": "function",
            "function": {"name": fixture.NAME, "arguments": json.dumps(probe.tool_calls[0].arguments)}}]},
        {"role": "tool", "name": fixture.NAME, "tool_call_id": probe.tool_calls[0].call_id, "content": json.dumps(data)}]
    turn.iteration, turn.request.prompt = 2, "Continue using the verified tool result."
    response = await dispatch("POST", "/aryn/turn", turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    probe_final = ToolTurnResult.model_validate_json(response.body)
    assert probe_final.result.status.value == "completed" and not probe_final.tool_calls
    assert json.loads(probe_final.result.output) == {"summary": data["text"]}
    assert probe_final.result.model_evidence.origin == "isolated_test_double"
    assert probe_final.result.model_evidence.runtime_configuration == proposed.result.model_evidence.runtime_configuration
    assert network_attempts == [] and len(calls) == 12
    print("REAL_HERMES_FIXED_CAPABILITY_PROBE_PASS")
    # Actual installed Hermes consumes Core declarations but never imports or
    # dispatches MCP. Protocol integration is tested separately through Core.
    from packages.contracts.tool import ToolDeclaration
    declaration = ToolDeclaration(name="aryn_mcp_project_lookup", input_schema={"type": "object",
        "properties": {"key": {"enum": ["aryn-core"]}}, "required": ["key"], "additionalProperties": False})
    mcp_turn = ToolTurnRequest(run_id="core_mcp_run", organization_id="isolated-org", project_id="isolated-project",
        iteration=1, tool_names=[declaration.name], tool_declarations=[declaration],
        request=RunRequest(model="test/mcp-tool-model", max_tokens=128, prompt="Read approved MCP resource.",
            metadata={"initial_prompt": "Read approved MCP resource."}))
    invalid = mcp_turn.model_dump(mode="json")
    invalid["tool_names"] = ["terminal"]
    assert (await dispatch("POST", "/aryn/turn", invalid)).status == 422
    invalid = mcp_turn.model_dump(mode="json")
    invalid["tool_declarations"] = []
    assert (await dispatch("POST", "/aryn/turn", invalid)).status == 422
    assert len(calls) == 12
    response = await dispatch("POST", "/aryn/turn", mcp_turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    mcp_proposed = ToolTurnResult.model_validate_json(response.body)
    call = mcp_proposed.tool_calls[0]
    assert call.name == declaration.name and call.arguments == {"key": "aryn-core"}
    assert mcp_proposed.result.status.value == "running" and len(calls) == 13
    mcp_turn.iteration = 2
    mcp_turn.history = [{"role": "user", "content": mcp_turn.request.prompt},
        {"role": "assistant", "content": "", "tool_calls": [{"id": call.call_id, "type": "function",
            "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}]},
        {"role": "tool", "name": call.name, "tool_call_id": call.call_id, "content": json.dumps(data)}]
    mcp_turn.request.prompt = "Continue using the verified tool result."
    response = await dispatch("POST", "/aryn/turn", mcp_turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    mcp_final = ToolTurnResult.model_validate_json(response.body)
    assert mcp_final.result.status.value == "completed" and not mcp_final.tool_calls
    assert json.loads(mcp_final.result.output) == {"summary": data["text"]}
    assert mcp_final.result.actual_model == "test/mcp-tool-model"
    assert mcp_final.result.model_evidence.origin == "isolated_test_double"
    assert len(calls) == 14 and network_attempts == []
    print("REAL_HERMES_MCP_DECLARATION_CONTINUATION_PASS")
    from packages.contracts.tool import HTTPS_INPUT_SCHEMA
    declaration = ToolDeclaration(name="aryn_https_project_lookup", input_schema=HTTPS_INPUT_SCHEMA)
    https_turn = ToolTurnRequest(run_id="core_https_run", organization_id="isolated-org", project_id="isolated-project",
        iteration=1, tool_names=[declaration.name], tool_declarations=[declaration],
        request=RunRequest(model="test/https-tool-model", max_tokens=128, prompt="Read approved resource.",
            metadata={"initial_prompt": "Read approved resource."}))
    response = await dispatch("POST", "/aryn/turn", https_turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    proposed = ToolTurnResult.model_validate_json(response.body)
    call = proposed.tool_calls[0]
    assert call.name == declaration.name and call.arguments == {"key": "aryn-core"}
    https_turn.iteration = 2
    https_turn.history = [{"role": "user", "content": https_turn.request.prompt},
        {"role": "assistant", "content": "", "tool_calls": [{"id": call.call_id, "type": "function",
            "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}]},
        {"role": "tool", "name": call.name, "tool_call_id": call.call_id, "content": json.dumps(data)}]
    https_turn.request.prompt = "Continue using the verified tool result."
    response = await dispatch("POST", "/aryn/turn", https_turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    final = ToolTurnResult.model_validate_json(response.body)
    assert final.result.status.value == "completed" and not final.tool_calls
    assert final.result.actual_model == "test/https-tool-model"
    assert json.loads(final.result.output) == {"summary": data["text"]}
    assert len(calls) == 16 and network_attempts == []
    print("REAL_HERMES_HTTPS_DECLARATION_CONTINUATION_PASS")
    from packages.contracts.tool import GITHUB_ISSUE_TOOL, GITHUB_ISSUE_INPUT
    declaration = ToolDeclaration(name=GITHUB_ISSUE_TOOL, input_schema=GITHUB_ISSUE_INPUT)
    github_turn = ToolTurnRequest(run_id="core_github_run", organization_id="isolated-org", project_id="isolated-project",
        iteration=1, tool_names=[declaration.name], tool_declarations=[declaration],
        request=RunRequest(model="test/github-tool-model", max_tokens=128, prompt="Read approved issue 42.",
            metadata={"initial_prompt": "Read approved issue 42."}))
    response = await dispatch("POST", "/aryn/turn", github_turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    proposed = ToolTurnResult.model_validate_json(response.body)
    call = proposed.tool_calls[0]
    assert call.name == declaration.name and call.arguments == {"issue_number": 42}
    assert proposed.result.status.value == "running"
    github_turn.iteration = 2
    github_turn.history = [{"role": "user", "content": github_turn.request.prompt},
        {"role": "assistant", "content": "", "tool_calls": [{"id": call.call_id, "type": "function",
            "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}]},
        {"role": "tool", "name": call.name, "tool_call_id": call.call_id,
            "content": json.dumps({"title": "Synthetic issue 42", "state": "open", "content_trust": "untrusted", "source": "github_https_fixture"})}]
    github_turn.request.prompt = "Continue using the verified tool result."
    response = await dispatch("POST", "/aryn/turn", github_turn.model_dump(mode="json"))
    assert response.status == 200, response.body
    final = ToolTurnResult.model_validate_json(response.body)
    assert final.result.status.value == "completed" and not final.tool_calls
    assert final.result.actual_model == "test/github-tool-model"
    assert json.loads(final.result.output) == {"summary": "Synthetic issue 42: open"}
    assert len(calls) == 18 and network_attempts == []
    print("REAL_HERMES_GITHUB_DECLARATION_CONTINUATION_PASS")
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
