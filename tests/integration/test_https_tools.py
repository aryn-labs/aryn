"""Offline Core/Factory/Bench vertical slice through real loopback TLS sockets."""
import asyncio
import json
import time

import pytest

from modules.core.tools import CoreTools
from modules.core.permissions.engine import PermissionDeniedError
from packages.contracts.core import Actor, SecurityContext
from packages.contracts.model import ModelCapabilities
from packages.contracts.runtime import RunResult, RunStatus, RunUsage, ToolCall, ToolTurnResult
from tests.conftest import bind_test_context
from tests.https_fixture import ALIAS, CAPABILITY, TEXT, definition, https_server as https_server
from tests.studio_runtime import IsolatedTestRuntime


class HTTPSModelDouble(IsolatedTestRuntime):
    def __init__(self):
        super().__init__()
        self.turns, self.results = [], []
        self.proposal = {"call_id": "https_lookup", "name": ALIAS, "arguments": {"key": "aryn-core"}}
        self.before_result = None
        self.repeat = self.escalate = False
        self.provider = "https-model-double"

    async def capabilities(self):
        caps = await super().capabilities()
        caps.supports_governed_tool_turns = True
        return caps

    async def model_capabilities(self, model):
        return ModelCapabilities(model=model, text_generation="supported", tool_calling="supported", source="https_model_double")

    async def execute_tool_turn(self, turn, ctx):
        self.turns.append(turn.model_copy(deep=True))
        if self.before_result:
            await self.before_result(turn)
        calls, output = [], {"summary": TEXT}
        if turn.tool_names and (not turn.history or self.repeat):
            assert [item.name for item in turn.tool_declarations] == [ALIAS]
            calls = [ToolCall(**self.proposal)]
        elif turn.history:
            data = json.loads(next(item for item in reversed(turn.history) if item["role"] == "tool")["content"])
            self.results.append(data)
            output = {"summary": data["text"]}
            if self.escalate:
                calls = [ToolCall(call_id="escalation", name="terminal", arguments={})]
        result = RunResult(run_id=f"https_model_{len(self.turns)}", model=turn.request.model,
            requested_model=turn.request.model, actual_model=turn.request.model, provider=self.provider,
            runtime_backend="Hermes", gateway="9Router", status=RunStatus.RUNNING if calls else RunStatus.COMPLETED,
            output="" if calls else json.dumps(output), created_at=time.time(),
            usage=RunUsage(input_tokens=10, output_tokens=5, total_tokens=15))
        return ToolTurnResult(run_id=turn.run_id, iteration=turn.iteration, result=result, tool_calls=calls)


async def published_https(lifecycle, state, **updates):
    db, ctx, _, factory, bp, _ = lifecycle
    core = factory.execution_coordinator
    core.mcp_tools = CoreTools(core, https_trust=state.trust)
    runtime = HTTPSModelDouble()
    factory.bench_runner.runtime_adapter = core.runtime_adapter = runtime
    approval = await core.mcp_tools.register(ctx, definition(state, ctx, **updates), state.secret)
    version = factory.create_version(ctx, bp.id, "3.1.0", "Read the approved resource; return its text as JSON summary.", "mock-fast",
        tool_grants=[ALIAS], metadata={"https_bindings": {ALIAS: approval.binding_hash}},
        evaluation_reference={"suite_id": "governed-https"}, output_contract={"format": "json", "strict": True,
            "schema_definition": {"type": "object", "properties": {"summary": {"const": TEXT}},
                "required": ["summary"], "additionalProperties": False}})
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    assert evaluation.passed, evaluation.model_dump_json()
    factory.approve_version(ctx, version.id)
    factory.publish_version(ctx, version.id)
    assignment = factory.assign_agent(ctx, bp.id, version.id, "Approved HTTPS read")
    state.requests.clear()
    runtime.turns.clear()
    runtime.results.clear()
    return db, ctx, runtime, core, assignment, approval, evaluation


async def test_published_https_transport_signed_history_and_continuation(lifecycle, https_server, caplog):
    db, ctx, runtime, core, assignment, approval, evaluation = await published_https(lifecycle, https_server)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read scoped data.", ctx, "https-e2e")
    assert result.status == RunStatus.COMPLETED and json.loads(result.output) == {"summary": TEXT}
    assert result.execution_claim_verified and result.assignment_provenance_verified and result.usage.total_tokens == 30
    assert len(https_server.requests) == 1 and len(runtime.turns) == 2
    assert https_server.requests[0]["line"] == "GET /records/aryn-core HTTP/1.1"
    assert https_server.requests[0]["tls"] in {"TLSv1.2", "TLSv1.3"}
    assert result.execution_evidence["actions"] == [{"action_id": "https_lookup", "action": "https.read", "tool": ALIAS, "capability": CAPABILITY}]
    events = core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx)
    proof = next(event.redacted_payload["https_provenance"] for event in events
        if event.resource_id == result.run_id and event.event_type == "core.tool.result")
    assert proof["network_requests"] == 1 and proof["tls_verified"] and proof["http_status"] == 200
    assert proof["binding_hash"] == approval.binding_hash and proof["trace_id"] == ctx.correlation_id
    assert proof["schema_hash"] == approval.connection.schema_hash and proof["validation"] == "schema_valid"
    assert db.evidence_signer.verify("https_connection_approval", approval.payload(), approval.attestation)
    trace = await core.get_managed_trace(result.run_id, ctx)
    assert trace.available and await core.get_managed_result(result.run_id, ctx) == result
    assert await core.execute_assigned_agent_turn(assignment.id, "Read scoped data.", ctx, "https-e2e") == result
    assert len(https_server.requests) == 1
    from database.schema import AuditEventModel
    from database.repositories.audit_repo import AuditRepository
    with db.session() as session:
        signed = session.query(AuditEventModel).filter_by(resource_id=result.run_id).all()
        assert signed and all(AuditRepository(session).verify_authenticated_event(row) for row in signed)
    serialized = str(events) + result.model_dump_json() + trace.model_dump_json() + caplog.text + evaluation.model_dump_json()
    serialized += json.dumps([turn.model_dump(mode="json") for turn in runtime.turns])
    assert https_server.secret.get_secret_value() not in serialized and https_server.endpoint not in serialized
    from pathlib import Path
    if db.engine.dialect.name == "sqlite":
        assert https_server.secret.get_secret_value().encode() not in Path(db.engine.url.database).read_bytes()
    import logging
    logging.getLogger("aryn.https.test").warning("Synthetic reflection %s", https_server.secret.get_secret_value())
    assert https_server.secret.get_secret_value() not in caplog.text and "[REDACTED]" in caplog.text
    from modules.core.capabilities import Capabilities
    capabilities = {row["namespace"]: row for row in Capabilities(core).read(ctx, "local", True)["capabilities"]}
    assert capabilities[CAPABILITY]["available"] and capabilities[CAPABILITY]["grants"] == []
    assert capabilities["aryn.https.adapter"]["available"] and capabilities["aryn.https.temporary_binding"]["available"]
    for name in ("external_connectivity", "persistent_credentials", "oauth"):
        assert not capabilities["aryn.https." + name]["available"]


@pytest.mark.parametrize("mode", ["malformed", "oversized", "wrong_type", "error", "redirect", "compressed", "chunked",
    "duplicate_header", "header_overflow", "truncated", "disconnect", "scope", "extra", "secret", "encoded_secret", "duplicate_json"])
async def test_response_failure_has_no_continuation_or_secret(lifecycle, https_server, caplog, mode):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    https_server.mode = mode
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-response-" + mode)
    assert result.status == RunStatus.FAILED and result.error_code == "tool_failed"
    assert len(runtime.turns) == len(https_server.requests) == 1 and not runtime.results
    assert https_server.secret.get_secret_value() not in caplog.text + result.model_dump_json()


@pytest.mark.parametrize("arguments", [{"url": "https://169.254.169.254/"}, {"key": "../private"}, {"key": "a%2fb"},
    {"key": "a\r\nHost: other"}, {"key": "a\n"}, {"key": "a" * 65}, {"key": 1}, {"key": "a", "headers": {}},
    {"key": "a", "project_id": "foreign"}, {"key": "a", "Authorization": "other"}])
async def test_proposal_cannot_select_network_scope_or_auth(lifecycle, https_server, arguments):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    runtime.proposal["arguments"] = arguments
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-input")
    assert result.status == RunStatus.FAILED and not https_server.requests and len(runtime.turns) == 1


@pytest.mark.parametrize("drift", ["revoked", "rotated", "expired", "stale", "endpoint", "schema", "secret", "approval", "assignment", "membership"])
async def test_authority_changes_before_dispatch_deny(lifecycle, https_server, monkeypatch, drift):
    from database.schema import MembershipModel
    db, ctx, runtime, core, assignment, approval, _ = await published_https(lifecycle, https_server)
    entry = core.mcp_tools.current(ctx, ALIAS)
    async def change(turn):
        if drift in {"revoked", "rotated"}:
            core.mcp_tools.revoke(ctx, approval.connection.connection_id)
            if drift == "rotated":
                from pydantic import SecretStr
                https_server.secret = SecretStr("rotated-synthetic-" + "b" * 48)
                await core.mcp_tools.register(ctx, definition(https_server, ctx), https_server.secret)
        elif drift in {"expired", "stale"}:
            monkeypatch.setattr("modules.core.tools.clock", lambda: approval.observed_at + (301 if drift == "expired" else 61))
        elif drift in {"endpoint", "schema"}:
            spec = entry.approval.connection
            updates = {"endpoint": "https://127.0.0.1:1"} if drift == "endpoint" else {"output_schema": {"type": "object"}}
            entry.approval = entry.approval.model_copy(update={"connection": spec.model_copy(update=updates)})
        elif drift == "secret":
            from pydantic import SecretStr
            entry.adapter._secret = SecretStr("other-synthetic-" + "c" * 48)
        elif drift == "approval":
            entry.approval = entry.approval.model_copy(update={"attestation": "forged"})
        elif drift == "assignment":
            # Simulate a current assignment becoming unavailable at Core readback.
            with db.session(write=True) as session:
                from database.schema import AgentAssignmentModel
                session.query(AgentAssignmentModel).filter_by(id=assignment.id).update({"status": "paused"})
        else:
            with db.session(write=True) as session:
                session.query(MembershipModel).filter_by(organization_id="org", user_id="owner").update({"status": "revoked"})
    runtime.before_result = change
    with pytest.raises(PermissionDeniedError):
        await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-drift-" + drift)
    from database.schema import RunStateModel
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="https-drift-" + drift).one()
        # Existing Core retains reservations when inference already ran but its
        # result cannot be safely accepted; this must never become success/retry.
        assert row.status == "outcome_unknown" and row.reserved_tokens > 0 and not row.usage_settled
    assert not https_server.requests and not runtime.results


@pytest.mark.parametrize("field", ["project_id", "binding_hash", "invocation_hash", "response_digest", "target_hash", "output_hash", "data"])
async def test_forged_transport_evidence_is_denied(lifecycle, https_server, monkeypatch, field):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    adapter = core.mcp_tools.current(ctx, ALIAS).adapter
    native = adapter.invoke
    async def forged(*args):
        data, proof = await native(*args)
        if field == "data":
            data["text"] = "forged result"
        else:
            proof[field] = "foreign" if field == "project_id" else "0" * 64
        return data, proof
    monkeypatch.setattr(adapter, "invoke", forged)
    with pytest.raises(PermissionDeniedError):
        await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-forged-" + field)
    assert len(https_server.requests) == 1 and len(runtime.turns) == 1


async def test_simulated_response_without_physical_dispatch_has_no_valid_receipt(lifecycle, https_server, monkeypatch):
    from packages.contracts.bench import evidence_hash
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    adapter = core.mcp_tools.current(ctx, ALIAS).adapter
    template = next(dict(event.redacted_payload["https_provenance"])
        for event in core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx)
        if event.event_type == "core.tool.result" and "https_provenance" in event.redacted_payload)
    async def simulated(arguments, invocation, *args):
        data = {"organization_id": ctx.organization_id, "project_id": ctx.project_id, "text": TEXT}
        proof = {**template, "run_id": invocation.run_id, "trace_id": invocation.trace_id, "call_id": invocation.call_id,
            "invocation_hash": evidence_hash(invocation.model_dump(mode="json")), "output_hash": evidence_hash(data)}
        return data, proof
    monkeypatch.setattr(adapter, "invoke", simulated)
    with pytest.raises(PermissionDeniedError):
        await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-no-dispatch")
    assert not https_server.requests and len(runtime.turns) == 1 and not runtime.results


async def test_response_injection_cannot_acquire_host_tool(lifecycle, https_server):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    https_server.mode, runtime.escalate = "injection", True
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-injection")
    assert result.status == RunStatus.FAILED and result.error_code == "tool_permission_denied"
    assert len(https_server.requests) == 1 and len(runtime.turns) == 2


@pytest.mark.parametrize("scope", ["unauthorized", "project", "tenant", "identity"])
async def test_actor_and_scope_cannot_use_approval(lifecycle, https_server, scope):
    _, ctx, _, core, assignment, _, _ = await published_https(lifecycle, https_server)
    other = SecurityContext(actor=Actor(actor_id="outsider", organization_id="org", roles=["admin"]), organization_id="org", project_id="project")
    if scope == "project":
        other = ctx.model_copy(update={"project_id": "foreign"})
    if scope == "tenant":
        other = ctx.model_copy(update={"organization_id": "foreign"})
    other = other if scope == "identity" else bind_test_context(other)
    with pytest.raises((PermissionDeniedError, LookupError)):
        await core.execute_assigned_agent_turn(assignment.id, "Read.", other, "https-scope")
    assert not https_server.requests


async def test_duplicate_proposal_cannot_dispatch_twice(lifecycle, https_server):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    runtime.repeat = True
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-duplicate")
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert len(https_server.requests) == 1


async def test_provider_fallback_cannot_be_verified(lifecycle, https_server):
    from packages.contracts.runtime import ModelIdentityError
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    async def change(turn):
        if turn.history:
            runtime.provider = "unauthorized-fallback"
    runtime.before_result = change
    with pytest.raises(ModelIdentityError):
        await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-provider")
    assert len(https_server.requests) == 1


async def test_core_cancellation_fences_pending_model_and_duplicate_claim(lifecycle, https_server):
    from modules.core.workflows.coordinator import RunInProgressError
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    entered, release = asyncio.Event(), asyncio.Event()
    async def wait(turn):
        entered.set()
        await release.wait()
    runtime.before_result = wait
    task = asyncio.create_task(core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-cancel"))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        with pytest.raises(RunInProgressError):
            await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-cancel")
        assert not await core.cancel_managed_run(runtime.turns[0].run_id, ctx)
    finally:
        release.set()
    with pytest.raises(PermissionDeniedError):
        await task
    assert not https_server.requests and len(runtime.turns) == 1


async def test_core_timeout_keeps_unknown_reservation_and_never_retries(lifecycle, https_server):
    from database.schema import RunStateModel
    db, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    https_server.mode = "wait"
    with pytest.raises(TimeoutError):
        await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-timeout")
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="https-timeout").one()
        assert row.status == "outcome_unknown" and row.reserved_tokens > 0 and not row.usage_settled
    stored = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-timeout")
    assert stored.status == RunStatus.OUTCOME_UNKNOWN and len(https_server.requests) == len(runtime.turns) == 1


async def test_budget_exhaustion_prevents_https_dispatch(lifecycle, https_server, monkeypatch):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    native = runtime.execute_tool_turn
    async def exhausted(*args):
        turn = await native(*args)
        turn.result.usage = RunUsage(input_tokens=100000, output_tokens=5, total_tokens=100005)
        return turn
    monkeypatch.setattr(runtime, "execute_tool_turn", exhausted)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-budget")
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert not https_server.requests


async def test_ungranted_tool_is_denied(lifecycle, https_server):
    _, ctx, runtime, core, assignment, _, _ = await published_https(lifecycle, https_server)
    runtime.proposal["name"] = "aryn_https_ungranted"
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "https-ungranted")
    assert result.status == RunStatus.FAILED and result.error_code == "tool_permission_denied"
    assert not https_server.requests
