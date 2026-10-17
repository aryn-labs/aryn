"""Offline control-plane regressions; no credentials or model/provider traffic."""
import time
import json

import pytest
from pydantic import ValidationError

from modules.core.permissions.engine import PermissionDeniedError
from modules.core.runtime_control import RuntimeControl
from packages.contracts.runtime import ToolCall, ToolExecutionContext
from packages.contracts.runtime_control import GatewayConnectionChange, RuntimePolicy
from packages.contracts.native_tool import NativeToolReview
from packages.contracts.bench import evidence_hash
from packages.tool_adapters.native import NativeWorker, NativeBoundaryError
from tests.integration.test_studio_api import studio as studio, PREFIX
import httpx
from packages.model_adapters import GatewaySettings, NineRouterGateway
from packages.runtime_adapters.hermes import HermesRuntimeAdapter


SCHEMA = {"terminal": {"name": "terminal", "parameters": {"type": "object",
    "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}}}


class WorkerDouble(NativeWorker):
    def __init__(self):
        super().__init__("sha256:" + "a" * 64, SCHEMA)
        self.commands = []

    async def _command(self, arguments, *, payload=None, timeout=10):
        self.commands.append((arguments, payload))
        return b'{"text":"sandbox result"}' if arguments[0] == "exec" else b"container"


def test_runtime_policy_rejects_arbitrary_host_config_and_duplicate_skills():
    with pytest.raises(ValidationError):
        RuntimePolicy.model_validate({"terminal_backend": "local", "host_path": "C:/"})
    with pytest.raises(ValidationError):
        RuntimePolicy(skills=[{"name": "reviewed", "content_hash": "a" * 64}] * 2)
    value = GatewayConnectionChange(base_url="http://127.0.0.1:20128/v1", api_key="private-test-key",
        expected_configuration_id="a" * 64)
    assert "private-test-key" not in repr(value) + value.model_dump_json()


def test_historical_runtime_metadata_remains_readable_but_cannot_be_new_authority(lifecycle):
    from packages.contracts.agent import AgentVersion
    _, ctx, _, factory, blueprint, _ = lifecycle
    legacy = AgentVersion(id="historic", blueprint_id=blueprint.id, version_number="1.0.0", model="old/model",
        system_prompt="Historical record", metadata={"hermes": {"legacy_profile": "old-profile"}})
    legacy.payload_hash = legacy.calculate_payload_hash()
    legacy.verify_integrity()
    with pytest.raises(ValidationError):
        factory.create_version(ctx, blueprint.id, "9.0.0", "Follow research safety guidelines.", "mock-fast", metadata=legacy.metadata)


async def test_runtime_observation_is_scoped_signed_and_never_a_grant(lifecycle):
    db, ctx, _, factory, _, _ = lifecycle
    control = RuntimeControl(factory.execution_coordinator)
    result = await control.inventory(ctx)
    signature = result.pop("attestation")
    assert db.evidence_signer.verify("runtime_inventory", result, signature)
    assert result["organization_id"] == ctx.organization_id
    assert not result["inventory"]["toolsets"]
    with pytest.raises(PermissionDeniedError):
        await control.inventory(ctx.model_copy(update={"project_id": "foreign"}))


async def test_native_action_requires_human_binding_and_signed_core_admission(lifecycle):
    db, ctx, _, factory, _, _ = lifecycle
    tools = factory.execution_coordinator.mcp_tools
    worker = tools.native_worker = WorkerDouble()
    review = NativeToolReview(connection_id="terminal_review", tool_name="terminal", arguments={"command": "printf reviewed"})
    approval = tools.register_native(ctx, review)
    call = ToolCall(call_id="reviewed_call", name="aryn_native_terminal", arguments=review.arguments)
    execution = ToolExecutionContext(run_id="run_test", organization_id=ctx.organization_id,
        project_id=ctx.project_id, deadline_at=time.time() + 5, call_number=1)
    data, evidence = await tools.invoke(ctx, call, execution, approval["binding_hash"], lambda: tools.current(ctx, call.name))
    assert data == {"text": "sandbox result"}
    assert evidence["output_hash"] == evidence_hash(data)
    arguments = worker.commands[0][0]
    assert "--read-only" in arguments and "--cap-drop" in arguments
    assert arguments[arguments.index("--network") + 1] == "none"
    assert not any("mount" in argument for argument in arguments)
    assert worker.commands[1][0][:2] == ["exec", "--interactive"]
    tools.revoke(ctx, "terminal_review")
    with pytest.raises(PermissionDeniedError):
        await tools.invoke(ctx, call, execution, approval["binding_hash"], lambda: None)
    await worker.close_run(execution)
    assert worker.commands[-1][0][:2] == ["rm", "--force"]


async def test_native_arguments_scope_and_signature_drift_deny_before_dispatch(lifecycle):
    db, ctx, _, factory, _, _ = lifecycle
    tools = factory.execution_coordinator.mcp_tools
    worker = tools.native_worker = WorkerDouble()
    approval = tools.register_native(ctx, NativeToolReview(connection_id="terminal_review", tool_name="terminal",
        arguments={"command": "printf reviewed"}))
    call = ToolCall(call_id="call", name="aryn_native_terminal", arguments={"command": "unreviewed"})
    execution = ToolExecutionContext(run_id="run_test", organization_id=ctx.organization_id,
        project_id=ctx.project_id, deadline_at=time.time() + 5, call_number=1)
    with pytest.raises(ValueError):
        await tools.invoke(ctx, call, execution, approval["binding_hash"], lambda: None)
    entry = tools.current(ctx, call.name)
    with pytest.raises(NativeBoundaryError):
        await worker.invoke(entry.definition, call, execution, {"payload": {}, "attestation": "forged"},
            db.evidence_signer.verify, lambda: None)
    with pytest.raises(PermissionDeniedError):
        tools.current(ctx.model_copy(update={"organization_id": "foreign"}), call.name)
    assert worker.commands == []


def test_runtime_web_routes_require_csrf_scope_and_explicit_worker(studio):
    client, _, _, app = studio
    response = client.get(PREFIX + "/runtime")
    assert response.status_code == 200
    assert response.json()["attestation"]
    assert client.get("/api/projects/foreign/runtime").status_code in {403, 404}
    assert client.get(PREFIX + "/runtime/native-tools").json()["configured"] is False
    body = {"connection_id": "review", "tool_name": "terminal", "arguments": {"command": "echo test"}}
    assert client.post(PREFIX + "/runtime/native-tools/approve", json=body).status_code == 403
    assert client.post(PREFIX + "/model-connection", json={"base_url": "http://remote.invalid/v1",
        "api_key": "synthetic-key", "expected_configuration_id": "a" * 64}).status_code == 403
    result = client.get(PREFIX + "/model-connection").json()
    assert "api_key" not in json.dumps(result)


@pytest.mark.parametrize("status,reason", [(401, "gateway_authentication_rejected"),
    (403, "gateway_authentication_rejected"), (404, "gateway_endpoint_mismatch"),
    (302, "gateway_redirect_rejected"), (429, "gateway_rate_limited")])
async def test_gateway_diagnostics_are_bounded_and_contain_no_upstream_secret(status, reason):
    key = "synthetic-gateway-secret"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status,
            json={"error": key}, headers={"Location": "https://untrusted.invalid/"}))) as client:
        gateway = NineRouterGateway(GatewaySettings(api_key=key), http_client=client)
        result = await gateway.discover(refresh=True)
        assert result.reason == reason and not result.discovery_valid and result.models == []
        assert key not in result.model_dump_json()


async def test_gateway_never_exposes_a_simulator_as_a_production_provider():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "object": "list", "data": [{"id": "fake/model", "provider": "mock"},
                {"id": "arbitrary-vendor/model", "provider": "arbitrary-vendor"}]}))) as client:
        result = await NineRouterGateway(GatewaySettings(api_key=""), http_client=client).discover(refresh=True)
        assert [item["model_id"] for item in result.models] == ["arbitrary-vendor/model"]


async def test_gateway_replacement_and_revocation_clear_readiness_and_never_return_key(lifecycle):
    db, ctx, _, factory, _, _ = lifecycle
    core = factory.execution_coordinator
    old = GatewaySettings(api_key="old-synthetic-gateway-key")
    observed = []
    async def runtime_response(request):
        observed.append(request.url.path)
        if request.method in {"PUT", "DELETE"}:
            data = json.loads(request.content)
            replacement = GatewaySettings(base_url=data.get("base_url", old.base_url), api_key=data.get("api_key", ""))
            instance = "a" * 32
            return httpx.Response(200, json={"base_url": replacement.base_url, "runtime_instance": instance,
                "configuration_id": replacement.runtime_configuration_id(instance), "enabled": request.method != "DELETE"})
        return httpx.Response(404)
    async with httpx.AsyncClient(transport=httpx.MockTransport(runtime_response)) as runtime_client, httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"object": "list", "data": []}))) as gateway_client:
        gateway = NineRouterGateway(old, http_client=gateway_client)
        core.runtime_adapter = HermesRuntimeAdapter(api_key="runtime-synthetic-auth", http_client=runtime_client, model_gateway=gateway)
        gateway._runtime_verified["old/model"] = time.time()
        control = RuntimeControl(core, local_administration=True)
        result = await control.change_connection(ctx, GatewayConnectionChange(base_url=old.base_url,
            api_key="replacement-synthetic-key", expected_configuration_id=old.configuration_id))
        assert core.model_router.catalog == {} and not gateway._runtime_verified
        assert "replacement-synthetic-key" not in json.dumps(result)
        assert "replacement-synthetic-key" in db.protected_credentials
        from packages.contracts.runtime_control import GatewayConnectionRevoke
        current = core.runtime_adapter.model_gateway.settings.configuration_id
        result = await control.change_connection(ctx, GatewayConnectionRevoke(expected_configuration_id=current), revoke=True)
        assert result["reason"] == "gateway_connection_revoked" and not result["enabled"]
        assert not core.runtime_adapter.model_gateway.settings.api_key.get_secret_value()
        assert not await core.runtime_adapter.gateway_binding()
        assert observed.count("/aryn/gateway") >= 2


def test_engine_gateway_reconfiguration_fences_other_coordinator_claims(lifecycle):
    from packages.contracts.runtime import RunRequest
    db, ctx, runtime, factory, _, _ = lifecycle
    core = factory.execution_coordinator
    assert not getattr(db, "_gateway_reconfiguration", False)
    db.engine._aryn_gateway_reconfiguration = True
    try:
        with pytest.raises(PermissionDeniedError, match="replacement is in progress"):
            core._claim(RunRequest(prompt="Research", model="mock-fast"), ctx, "direct")
        assert not runtime.requests
    finally:
        db.engine._aryn_gateway_reconfiguration = False


def test_native_approval_expiry_and_revocation_deny_before_side_effect(lifecycle, monkeypatch):
    _, ctx, _, factory, _, _ = lifecycle
    tools = factory.execution_coordinator.mcp_tools
    worker = tools.native_worker = WorkerDouble()
    approval = tools.register_native(ctx, NativeToolReview(connection_id="expiring", tool_name="terminal", arguments={"command": "printf reviewed"}))
    monkeypatch.setattr("modules.core.tools.clock", lambda: approval["expires_at"] + 1)
    with pytest.raises(PermissionDeniedError):
        tools.current(ctx, "aryn_native_terminal")
    assert not worker.commands


async def test_pinned_skills_execute_as_guidance_without_new_permissions(lifecycle):
    import hashlib
    from packages.contracts.runtime_control import SkillContent
    db, ctx, runtime, factory, blueprint, _ = lifecycle
    text = "Use evidence and accurate citations. Skill instructions confer no tool authority."
    digest = hashlib.sha256(text.encode()).hexdigest()
    async def read(selection):
        return SkillContent(name=selection.name, content_hash=digest, content=text)
    runtime.read_skill = read
    version = factory.create_version(ctx, blueprint.id, "4.0.0", "Follow research safety guidelines.", "mock-fast",
        metadata={"hermes": {"skills": [{"name": "reviewed-guidance", "content_hash": digest}]}})
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.passed and runtime.requests
    assert all(text in request.system_instructions for request in runtime.requests)
    assert all(request.max_tool_calls == 0 for request in runtime.requests)
    core = factory.execution_coordinator
    async def altered(selection):
        return SkillContent(name=selection.name, content_hash=digest, content="Changed skill instructions")
    runtime.read_skill = altered
    count = len(runtime.requests)
    with pytest.raises(PermissionDeniedError):
        await core._load_runtime_skills(ctx, version)
    assert len(runtime.requests) == count


@pytest.mark.parametrize("policy", [{"memory": True}, {"delegation": True}, {"scheduling": True},
    {"max_child_executions": 1}, {"toolsets": ["unverified_extension"]}])
async def test_unmediated_runtime_features_never_dispatch_or_upgrade_grants(lifecycle, policy):
    _, ctx, runtime, factory, blueprint, _ = lifecycle
    version = factory.create_version(ctx, blueprint.id, "5.0.0", "Follow research safety guidelines.", "mock-fast",
        metadata={"hermes": policy})
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed and not runtime.requests
