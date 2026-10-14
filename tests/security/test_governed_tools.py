"""Offline model double + actual Core/Factory/Bench/fixture executor; no live inference."""
import asyncio
import json
import time

import httpx
import pytest

from database.repositories.budget_repo import BudgetRepository
from database.repositories.run_state_repo import RunStateRepository
from database.schema import MembershipModel, RunStateModel
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.workflows.coordinator import RunInProgressError
from packages.contracts.bench import validate_output, OutputContract
from packages.contracts.model import ModelCapabilities
from packages.contracts.runtime import ModelIdentityError, RunResult, RunStatus, RunUsage, ToolCall, ToolTurnResult
from packages.tool_adapters import fixture
from tests.studio_runtime import IsolatedTestRuntime
from tests.conftest import bind_test_context


class ToolModelDouble(IsolatedTestRuntime):
    """A labeled model double which never executes a tool itself."""
    def __init__(self, provider="model-test-double"):
        super().__init__()
        self.provider = provider
        self.turns = []
        self.proposal = {"call_id": "fixture_call", "name": fixture.NAME, "arguments": {"key": "aryn-core"}}
        self.force_proposal = False
        self.repeat = False
        self.output = '{"summary":"ARYN Core owns execution authorization."}'
        self.tool_capability = "supported"
        self.enabled = True
        self.forged = False
        self.mismatch = False
        self.tokens = 15
        self.before_result = None

    async def capabilities(self):
        caps = await super().capabilities()
        caps.supports_governed_tool_turns = self.enabled
        caps.details = {"tool_isolation": "read_only_fixture"}
        return caps

    async def model_capabilities(self, model):
        return ModelCapabilities(model=model, text_generation="supported", tool_calling=self.tool_capability,
            structured_output="unknown", source="explicit_model_test_double")

    async def execute_tool_turn(self, turn, context):
        self.turns.append(turn.model_copy(deep=True))
        if self.before_result:
            await self.before_result(turn)
        proposing = (turn.tool_names or self.force_proposal) and (not turn.history or self.repeat)
        calls = [ToolCall(**self.proposal)] if proposing else []
        if turn.history and not proposing:
            result_message = next(m for m in turn.history if m.get("role") == "tool")
            assert json.loads(result_message["content"]) == fixture.FixtureOutput(
                key="aryn-core", text="ARYN Core owns execution authorization.").model_dump()
        result = RunResult(run_id=f"double_{len(self.turns)}", status=RunStatus.RUNNING if calls else RunStatus.COMPLETED,
            model="another-model" if self.mismatch else turn.request.model,
            requested_model=turn.request.model, actual_model=turn.request.model, gateway="9Router", runtime_backend="Hermes",
            output="" if calls else self.output, usage=RunUsage(input_tokens=10, output_tokens=self.tokens - 10, total_tokens=self.tokens),
            created_at=time.time(), provider=self.provider, execution_evidence={"run_id": turn.run_id} if self.forged else None)
        return ToolTurnResult(run_id=turn.run_id, iteration=turn.iteration, result=result, tool_calls=calls)


async def published(lifecycle, *, model="mock-fast", provider="model-test-double"):
    db, ctx, _, factory, bp, _ = lifecycle
    runtime = ToolModelDouble(provider)
    if model != "mock-fast":
        from packages.contracts.model import ModelSpec, ModelProviderType
        factory.model_router.catalog[model] = ModelSpec(model_id=model, display_name="Offline fixture", provider=ModelProviderType.NINE_ROUTER)
        factory.model_router.config.allowed_models.append(model)
    factory.bench_runner.runtime_adapter = runtime
    version = factory.create_version(ctx, bp.id, "2.0.0", "Use only explicitly granted tools; return JSON summary.",
        model, tool_grants=[fixture.NAME], evaluation_reference={"suite_id": "governed-fixture"},
        output_contract={"format": "json", "strict": True, "schema_definition": {
            "type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}})
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    assert evaluation.passed, [(r.state, [(g.reason, g.details) for g in r.grader_results]) for r in evaluation.scenario_results]
    factory.approve_version(ctx, version.id)
    factory.publish_version(ctx, version.id)
    assignment = factory.assign_agent(ctx, bp.id, version.id, "Fixture verification")
    runtime.turns.clear()
    return db, ctx, runtime, factory.execution_coordinator, assignment, evaluation


@pytest.mark.asyncio
@pytest.mark.parametrize("model,provider", [("ds/offline-fixture-a", "fixture-provider-a"),
    ("ag/offline-fixture-b", "fixture-provider-b")])
async def test_governed_agent_and_bench_preserve_exact_model_across_catalog_rename(lifecycle, model, provider):
    db, ctx, runtime, core, assignment, evaluation = await published(lifecycle, model=model, provider=provider)
    from database.repositories.agent_repo import AgentRepository
    def version_snapshot():
        with db.session() as session:
            row = AgentRepository(session).get_version(ctx, assignment.version_id)
            return {column.name: getattr(row, column.name) for column in row.__table__.columns}
    captured = version_snapshot()
    assert evaluation.passed and evaluation.requested_model == model
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "cross-provider-assigned")
    assert result.status == RunStatus.COMPLETED and result.actual_model == result.requested_model == model
    assert result.provider == provider and len(runtime.turns) == 2
    core.model_router.catalog[model].display_name = "Changed catalog label"
    assert version_snapshot() == captured
    assert await core.get_managed_result(result.run_id, ctx) == result
    assert await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "cross-provider-assigned") == result
    assert len(runtime.turns) == 2


@pytest.mark.asyncio
async def test_assigned_tool_continuation_is_persisted_and_idempotent(lifecycle):
    db, ctx, runtime, core, assignment, evaluation = await published(lifecycle)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "governed-once")
    assert result.status == RunStatus.COMPLETED
    assert json.loads(result.output)["summary"] == "ARYN Core owns execution authorization."
    assert len(runtime.turns) == 2 and result.usage.total_tokens == 30
    assert result.assignment_id == assignment.id and result.execution_claim_verified and result.assignment_provenance_verified
    assert result.execution_evidence["actions"][0]["tool"] == fixture.NAME
    assert result.execution_evidence["run_id"] == result.run_id
    assert await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "governed-once") == result
    assert await core.get_managed_result(result.run_id, ctx) == result
    trace = await core.get_managed_trace(result.run_id, ctx)
    assert trace.available and trace.raw_trace["source"] == "signed_core_audit"
    assert len(runtime.turns) == 2
    assert all(s.passed for s in evaluation.scenario_results)
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 0
        row = RunStateRepository(session).get_run(ctx, result.run_id)
        assert row.total_tokens == 30
    events = core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx)
    events = [e for e in events if e.resource_id == result.run_id]
    assert len([e for e in events if e.event_type == "core.run.iteration"]) == 2
    assert len([e for e in events if e.event_type == "core.tool.result"]) == 1
    assert all(e.attestation for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["organization", "project", "expired"])
async def test_foreign_scope_and_expired_identity_cannot_dispatch(lifecycle, boundary):
    _, ctx, runtime, core, assignment, _ = await published(lifecycle)
    foreign = ctx.model_copy(deep=True)
    if boundary == "organization":
        foreign.organization_id = foreign.actor.organization_id = "foreign"
    elif boundary == "project":
        foreign.project_id = "foreign"
    foreign = bind_test_context(foreign)
    if boundary == "expired":
        foreign = core.permission_engine.identity_binder.bind_context(foreign, ttl_seconds=-1)
    with pytest.raises((PermissionDeniedError, ValueError)):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", foreign, "foreign")
    assert not runtime.turns


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["audit", "output"])
async def test_signed_tool_evidence_tampering_fails_closed(lifecycle, target):
    from sqlalchemy import text
    from tests.storage_attacks import corrupt_storage
    _, ctx, _, core, assignment, _ = await published(lifecycle)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "tamper")
    if target == "audit":
        with corrupt_storage(core.db_manager.engine) as connection:
            connection.execute(text("UPDATE audit_events SET redacted_payload_json='{}' WHERE resource_id=:run AND event_type='core.run.evidence'"),
                {"run": result.run_id})
    else:
        with core.db_manager.engine.begin() as connection:
            connection.execute(text("UPDATE run_states SET output='forged result' WHERE id=:run"), {"run": result.run_id})
    with pytest.raises(PermissionDeniedError):
        await core.get_managed_result(result.run_id, ctx)


@pytest.mark.asyncio
async def test_permission_revoked_between_model_steps_prevents_continuation(lifecycle):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    native = runtime.model_capabilities
    async def revoke(model):
        if len(runtime.turns) == 1:
            with db.session(write=True) as session:
                session.query(MembershipModel).filter_by(user_id="owner").one().status = "revoked"
        return await native(model)
    runtime.model_capabilities = revoke
    with pytest.raises(PermissionDeniedError):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "between-steps")
    assert len(runtime.turns) == 1


@pytest.mark.asyncio
async def test_secrets_are_redacted_from_result_audit_and_trace(lifecycle):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    secret = "registered-fixture-credential"
    db.protected_credentials = (secret,)
    runtime.output = json.dumps({"summary": secret})
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "redacted")
    assert result.status == RunStatus.COMPLETED and secret not in result.model_dump_json()
    events = core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx)
    assert secret not in json.dumps([e.model_dump(mode="json") for e in events])
    assert secret not in (await core.get_managed_trace(result.run_id, ctx)).model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("case,code", [
    ("unknown", "tool_permission_denied"), ("schema", "tool_input_invalid"),
    ("missing", "tool_failed"), ("duplicate", "execution_limit_exceeded"),
    ("limit", "execution_limit_exceeded"), ("output", "invalid_output"),
])
async def test_tool_errors_and_limits_never_become_success(lifecycle, monkeypatch, case, code):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    effects = []
    execute = fixture.execute
    def counted(arguments, context):
        effects.append(context.run_id)
        return execute(arguments, context)
    monkeypatch.setattr(fixture, "execute", counted)
    if case == "unknown":
        runtime.proposal["name"] = "terminal"
    elif case == "schema":
        runtime.proposal["arguments"] = {"key": "aryn-core", "path": "secret"}
    elif case == "missing":
        runtime.proposal["arguments"] = {"key": "missing"}
    elif case == "duplicate":
        runtime.repeat = True
    elif case == "limit":
        runtime.tokens = 5000
    else:
        runtime.output = '{"summary":12}'
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "negative")
    assert result.status == RunStatus.FAILED and result.error_code == code
    assert result.output == ""
    assert len(effects) <= 1
    if case in {"unknown", "limit"}:
        assert effects == []
    before = len(runtime.turns)
    assert await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "negative") == result
    assert len(runtime.turns) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["runtime", "model_capability", "identity", "forgery", "revocation", "timeout", "cancel"])
async def test_uncertainty_and_revocation_block_execution(lifecycle, monkeypatch, case):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    effects = []
    monkeypatch.setattr(fixture, "execute", lambda *args: effects.append(True))
    if case == "runtime":
        runtime.enabled = False
    elif case == "model_capability":
        runtime.tool_capability = "unknown"
    elif case == "identity":
        runtime.mismatch = True
    elif case == "forgery":
        runtime.forged = True
    elif case == "revocation":
        async def revoked(turn):
            with db.session(write=True) as session:
                session.query(MembershipModel).filter_by(user_id="owner").one().status = "revoked"
        runtime.before_result = revoked
    else:
        async def interrupted(turn):
            if case == "timeout":
                raise TimeoutError("secret upstream error")
            raise asyncio.CancelledError()
        runtime.before_result = interrupted
    expected = ModelIdentityError if case == "identity" else TimeoutError if case == "timeout" else asyncio.CancelledError if case == "cancel" else PermissionDeniedError
    with pytest.raises(expected):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "blocked")
    assert effects == []
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="blocked").one()
        assert row.status == ("failed" if case == "identity" else "outcome_unknown")
        assert row.reserved_tokens > 0
        assert "secret upstream" not in (row.error_message or "")


@pytest.mark.asyncio
async def test_concurrent_duplicate_cannot_dispatch_twice(lifecycle):
    _, ctx, runtime, core, assignment, _ = await published(lifecycle)
    entered, release = asyncio.Event(), asyncio.Event()
    async def block(turn):
        entered.set()
        await release.wait()
    runtime.before_result = block
    task = asyncio.create_task(core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "concurrent"))
    await asyncio.wait_for(entered.wait(), 5)
    with pytest.raises(RunInProgressError):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "concurrent")
    release.set()
    assert (await task).status == RunStatus.COMPLETED
    assert len(runtime.turns) == 2


@pytest.mark.asyncio
async def test_bench_no_grant_injection_cannot_execute_tool(lifecycle, monkeypatch):
    db, ctx, _, factory, bp, _ = lifecycle
    runtime = ToolModelDouble()
    runtime.force_proposal = True
    factory.bench_runner.runtime_adapter = runtime
    version = factory.create_version(ctx, bp.id, "2.0.0", "Do not infer grants from prompts.", "mock-fast",
        tool_grants=[fixture.NAME], evaluation_reference={"suite_id": "governed-fixture"})
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed
    denied = result.scenario_results[1]
    assert denied.runtime_status == "failed" and denied.execution.actions == []
    with db.session() as session:
        runs = session.query(RunStateModel).filter_by(execution_mode="governed_agent").all()
        assert len(runs) == 2 and runs[1].error_code == "tool_permission_denied"


@pytest.mark.parametrize("output", ['{"summary":1}', '{"summary":"ok","extra":1}',
    '{"summary":"a","summary":"b"}', '{"summary":NaN}', '```json\n{}\n```'])
def test_shared_output_validator_rejects_invalid_json(output):
    contract = OutputContract(format="json", strict=True, schema_definition={"type": "object",
        "properties": {"summary": {"type": "string"}}, "required": ["summary"]})
    assert validate_output(output, contract)[0] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["listing", "stale", "verified", "wrong_type", "missing_provider", "missing_configuration"])
async def test_model_capabilities_require_fresh_explicit_evidence(case):
    from packages.model_adapters.gateway import NineRouterGateway, GatewaySettings
    model = {"id": "test/model", "provider": "isolated-provider", "provider_configuration": "c" * 64,
        "supports_tools": True, "capabilities": {"tool_calling": "supported"}}
    if case != "listing":
        model.update(capabilities_verified=True, capabilities_source="runtime_probe",
            capabilities_checked_at=time.time() - (100 if case == "stale" else 0))
    if case == "wrong_type":
        model["capabilities"]["tool_calling"] = True
    if case == "missing_provider":
        model.pop("provider")
    if case == "missing_configuration":
        model.pop("provider_configuration")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,
            json={"object": "list", "data": [model]}))) as client:
        gateway = NineRouterGateway(GatewaySettings(), http_client=client)
        caps = await gateway.model_capabilities("test/model")
    assert caps.tool_calling == ("supported" if case == "verified" else "unknown")


@pytest.mark.asyncio
async def test_text_probe_never_establishes_tool_or_structured_capability():
    from packages.model_adapters.gateway import NineRouterGateway, GatewaySettings
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,
            json={"object": "list", "data": [{"id": "test/model"}]}))) as client:
        gateway = NineRouterGateway(GatewaySettings(), http_client=client)
        gateway.record_runtime_verification(RunResult(run_id="probe", status=RunStatus.COMPLETED, model="test/model",
            requested_model="test/model", actual_model="test/model", gateway="9Router", runtime_backend="Hermes",
            output="Ready", usage=RunUsage(input_tokens=1, output_tokens=1, total_tokens=2), created_at=time.time(),
            completed_at=time.time(), execution_claim_verified=True))
        caps = await gateway.model_capabilities("test/model")
        assert caps.text_generation == "supported"
        assert caps.tool_calling == caps.structured_output == "unknown"
        gateway.reject("test/model")
        assert (await gateway.model_capabilities("test/model")).text_generation == "unknown"


@pytest.mark.asyncio
async def test_budget_reduction_between_steps_denies_continuation(lifecycle):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    native = runtime.model_capabilities
    async def lowered(model):
        if len(runtime.turns) == 1:
            with db.session(write=True) as session:
                BudgetRepository(session).get_budget(ctx).max_turns = 1
        return await native(model)
    runtime.model_capabilities = lowered
    with pytest.raises(PermissionDeniedError, match="Budget authority"):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "reduced-budget")
    assert len(runtime.turns) == 1


@pytest.mark.asyncio
async def test_recovery_retains_unknown_tool_run_without_retry(lifecycle):
    from database.connection import DatabaseManager, create_db_engine
    from modules.core.workflows.coordinator import RunCoordinator
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    async def interrupted(turn):
        raise TimeoutError()
    runtime.before_result = interrupted
    with pytest.raises(TimeoutError):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "recovered")
    db_url = str(db.engine.url)
    db.engine.dispose()
    other_engine = create_db_engine(db_url)
    try:
        replacement = RunCoordinator(runtime, db_manager=DatabaseManager(other_engine))
        assert replacement.recover_in_flight_runs(ctx) == []  # Already honestly terminal unknown.
        result = await replacement.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "recovered")
        assert result.status == RunStatus.OUTCOME_UNKNOWN and len(runtime.turns) == 1
    finally:
        other_engine.dispose()


@pytest.mark.asyncio
async def test_three_iterations_never_allow_a_third_tool_effect(lifecycle, monkeypatch):
    _, ctx, runtime, core, assignment, _ = await published(lifecycle)
    runtime.repeat = True
    async def unique_call(turn):
        runtime.proposal["call_id"] = f"call_{turn.iteration}"
    runtime.before_result = unique_call
    effects = []
    execute = fixture.execute
    def counted(arguments, context):
        effects.append(context.call_number)
        return execute(arguments, context)
    monkeypatch.setattr(fixture, "execute", counted)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "bounded-turns")
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert len(runtime.turns) == 3 and effects == [1, 2]
    assert result.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_measured_cost_breach_blocks_tool_and_is_settled(lifecycle, monkeypatch):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    native = runtime.execute_tool_turn
    async def costly(turn, context):
        result = await native(turn, context)
        result.result.usage.cost_usd = 0.6
        result.result.usage.cost_source = "provider_usage"
        return result
    runtime.execute_tool_turn = costly
    effects = []
    monkeypatch.setattr(fixture, "execute", lambda *args: effects.append(True))
    result = await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "bounded-cost")
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert effects == [] and result.usage.cost_usd == 0.6
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["schema", "tool_error", "identity", "budget", "forged"])
async def test_bench_rejects_tool_faults_without_weakening_quality_gate(lifecycle, fault):
    _, ctx, _, factory, bp, _ = lifecycle
    runtime = ToolModelDouble()
    if fault == "schema":
        runtime.output = '{"summary": 1}'
    elif fault == "tool_error":
        runtime.proposal["arguments"] = {"key": "missing"}
    elif fault == "identity":
        runtime.mismatch = True
    elif fault == "budget":
        runtime.tokens = 5000
    else:
        runtime.forged = True
    factory.bench_runner.runtime_adapter = runtime
    version = factory.create_version(ctx, bp.id, "2.0.0", "Return fixture JSON summary.", "mock-fast",
        tool_grants=[fixture.NAME], evaluation_reference={"suite_id": "governed-fixture"})
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed and not result.quality_gate.passed
    assert result.scenario_results[0].state.value in {"runtime_error", "invalid_evidence", "policy_violation", "failed"}


def test_http_lifecycle_accepts_only_fixture_grant_and_runs_through_core(tmp_path):
    from fastapi.testclient import TestClient
    from database.connection import DatabaseManager, create_db_engine, init_db
    from services.api.studio import create_app
    from tests.integration.test_studio_api import ORIGIN, PREFIX, promoted
    db = DatabaseManager(create_db_engine(f"sqlite:///{tmp_path / 'tool-http.sqlite3'}"))
    init_db(db.engine)
    runtime = ToolModelDouble()
    try:
        with TestClient(create_app(db, runtime, testing=True), base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
            session = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
            assert session.status_code == 200
            client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrf"]})
            blueprint = client.post(PREFIX + "/blueprints", json={"name": "Fixture agent", "slug": "fixture-agent"}).json()
            path = PREFIX + f"/blueprints/{blueprint['id']}/versions"
            body = {"version_number": "1.0.0", "system_prompt": "Use only explicit tool grants and return a JSON summary.",
                "model": "test/model-a", "max_tokens": 512, "tool_grants": [fixture.NAME],
                "evaluation_reference": {"suite_id": "governed-fixture"},
                "output_contract": {"format": "json", "schema_definition": {"type": "object"}}}
            assert client.post(path, json={**body, "tool_grants": ["terminal"]}).status_code == 422
            response = client.post(path, json=body)
            assert response.status_code == 201, response.text
            version = response.json()
            denied = client.post(PREFIX + "/assignments", json={"blueprint_id": blueprint["id"],
                "version_id": version["id"], "role_name": "Verification"})
            assert 400 <= denied.status_code < 500 and not runtime.turns
            assignment = promoted(client, blueprint, version)
            runtime.turns.clear()
            request = {"assignment_id": assignment["id"], "prompt": "Read aryn-core and summarize.",
                "allow_remote_model": True, "idempotency_key": "http-governed-fixture"}
            run = client.post(PREFIX + "/runs", json=request)
            assert run.status_code == 200, run.text
            assert run.json()["status"] == "completed" and run.json()["total_tokens"] == 30
            assert run.json()["assignment_id"] == assignment["id"] and run.json()["execution_claim_verified"]
            assert client.post(PREFIX + "/runs", json=request).json() == run.json()
            assert len(runtime.turns) == 2
    finally:
        db.engine.dispose()


@pytest.mark.asyncio
async def test_explicit_core_stop_prevents_tool_after_inflight_model_returns(lifecycle, monkeypatch):
    db, ctx, runtime, core, assignment, _ = await published(lifecycle)
    effects = []
    monkeypatch.setattr(fixture, "execute", lambda *args: effects.append(True))
    async def stopped(turn):
        assert await core.cancel_managed_run(turn.run_id, ctx) is False
    runtime.before_result = stopped
    with pytest.raises(PermissionDeniedError):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "stopped")
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="stopped").one()
        assert row.status == "outcome_unknown" and row.reserved_tokens > 0
        run_id = row.id
    assert not effects and len(runtime.turns) == 1
    events = core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx)
    iterations = [e for e in events if e.event_type == "core.run.iteration" and e.resource_id == run_id]
    assert len(iterations) == 1 and iterations[0].redacted_payload["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_hermes_adapter_tool_turn_checks_scope_and_model_provenance():
    from packages.contracts.core import Actor, SecurityContext
    from packages.contracts.runtime import RunRequest, ToolTurnRequest
    from packages.runtime_adapters.hermes import RuntimeSecurityError
    from tests.gateway_fixtures import make_adapter, standard_handler, MODEL
    posts = []
    def handler(request):
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={"data": [], "governed_tool_turns": True,
                "tool_isolation": "read_only_fixture"})
        if request.url.path == "/aryn/turn":
            data = json.loads(request.content)
            posts.append(data)
            model = data["request"]["model"]
            result = RunResult(run_id="native-step", model=model, actual_model=model, requested_model=model,
                gateway="9Router", runtime_backend="Hermes", output="", status=RunStatus.RUNNING,
                usage=RunUsage(input_tokens=1, output_tokens=1, total_tokens=2), created_at=time.time())
            return httpx.Response(200, json=ToolTurnResult(run_id=data["run_id"], iteration=data["iteration"],
                result=result, tool_calls=[ToolCall(call_id="fixture", name=fixture.NAME, arguments={"key": "aryn-core"})]).model_dump(mode="json"))
        return standard_handler(request)
    ctx = SecurityContext(actor=Actor(actor_id="tester", organization_id="org"), organization_id="org", project_id="project")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client)
        request = ToolTurnRequest(run_id="core-run", organization_id="org", project_id="project", iteration=1,
            request=RunRequest(prompt="Read aryn-core.", model=MODEL), tool_names=[fixture.NAME])
        proposed = await adapter.execute_tool_turn(request, ctx)
        assert proposed.run_id == request.run_id and proposed.result.status == RunStatus.RUNNING
        with pytest.raises(RuntimeSecurityError):
            await adapter.execute_tool_turn(request.model_copy(update={"project_id": "foreign"}), ctx)
        assert len(posts) == 1


def capability_probe_core(lifecycle):
    """Offline model double + real scoped Core; never a live capability issuer."""
    db, ctx, _, factory, _, _ = lifecycle
    runtime = ToolModelDouble()
    runtime.tool_capability = "unknown"
    core = factory.execution_coordinator
    core.runtime_adapter = runtime
    return db, ctx, runtime, core


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["provider_rate_limited", "provider_insufficient_credit", "provider_quota_exhausted", "provider_unavailable"])
async def test_provider_error_keeps_core_identity_reservation_and_prevents_repeated_effects(lifecycle, code):
    from packages.contracts.runtime import ProviderRequestError
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    async def rejected(turn):
        raise ProviderRequestError(code)
    runtime.before_result = rejected
    with pytest.raises(ProviderRequestError):
        await core.verify_model("mock-fast", ctx, "provider-error", mode="tool_calling")
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="provider-error").one()
        assert row.model == "mock-fast" and row.status == "outcome_unknown" and row.error_code == code
        assert row.reserved_tokens > 0 and not row.usage_settled
    repeated = await core.verify_model("mock-fast", ctx, "provider-error", mode="tool_calling")
    assert repeated.status == RunStatus.OUTCOME_UNKNOWN and repeated.error_code == code
    assert len(runtime.turns) == 1 and repeated.execution_evidence is None


@pytest.mark.asyncio
@pytest.mark.parametrize("model,provider", [("ds/offline-fixture-a", "fixture-provider-a"),
    ("ag/offline-fixture-b", "fixture-provider-b")])
async def test_capability_probe_is_provider_agnostic_without_live_attestation(lifecycle, model, provider):
    from packages.contracts.model import ModelSpec, ModelProviderType
    from packages.model_adapters.router import ModelRouter
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    core.model_router = ModelRouter(catalog={model: ModelSpec(model_id=model, display_name="Offline fixture",
        provider=ModelProviderType.NINE_ROUTER)})
    execute = runtime.execute_tool_turn
    async def isolated_turn(turn, context):
        result = await execute(turn, context)
        result.result.provider = provider
        return result
    runtime.execute_tool_turn = isolated_turn
    result = await core.verify_model(model, ctx, "multi-provider", mode="tool_calling")
    assert result.status == RunStatus.COMPLETED and result.model == result.actual_model == result.requested_model == model
    assert result.provider == provider and result.usage.total_tokens == 30
    assert len(runtime.turns) == 2 and all(t.request.model == model for t in runtime.turns)
    assert len(result.execution_evidence["actions"]) == 1
    proof = result.execution_evidence["capability_probe"]
    assert proof["model"] == model and proof["provider"] == provider and proof["binding"] is None
    assert db.evidence_signer.verify("model_capability_probe", proof, result.execution_evidence["capability_attestation"])
    assert await core.verify_model(model, ctx, "multi-provider", mode="tool_calling") == result
    assert len(runtime.turns) == 2
    assert (await runtime.model_capabilities(model)).tool_calling == "unknown"


def test_capability_receipt_rejects_provider_change_and_cross_model_replay(lifecycle):
    gateway, evidence, signer = capability_receipt_policy_fixture(lifecycle)
    signature = signer.sign("model_capability_probe", evidence.model_dump(mode="json"))
    assert gateway.record_tool_verification(evidence, signature, signer)
    assert gateway._verified_tool_probe("different/model") is None
    gateway._provider_identities[evidence.model] = "different-provider"
    assert gateway._verified_tool_probe(evidence.model) is None
    altered = evidence.model_copy(update={"model": "different/model"})
    assert not gateway.record_tool_verification(altered, signature, signer)


@pytest.mark.asyncio
async def test_capability_probe_unknown_runs_fixed_tool_and_continuation_without_live_attestation(lifecycle, monkeypatch):
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    effects = []
    execute = fixture.execute
    def tracked(arguments, context):
        effects.append(context)
        return execute(arguments, context)
    monkeypatch.setattr(fixture, "execute", tracked)
    issued = []
    async def forbidden_issuer(*args):
        issued.append(True)
        return True
    runtime.record_tool_verification = forbidden_issuer
    result = await core.verify_model("mock-fast", ctx, "tool-probe", mode="tool_calling")
    assert result.status == RunStatus.COMPLETED and result.usage.total_tokens == 30
    assert len(runtime.turns) == 2 and len(effects) == 1 and effects[0].run_id == result.run_id
    assert all(t.verification_mode == "tool_calling" for t in runtime.turns)
    assert json.loads(result.output) == {"summary": "ARYN Core owns execution authorization."}
    assert result.agent_version_id is None and result.assignment_id is None
    assert result.effective_limits["max_turns"] == 2 and result.effective_limits["max_tool_calls"] == 1
    proof = result.execution_evidence["capability_probe"]
    signature = result.execution_evidence["capability_attestation"]
    assert proof["binding"] is None
    assert db.evidence_signer.verify("model_capability_probe", proof, signature)
    assert not db.evidence_signer.verify("model_capability_probe", {**proof, "model": "foreign"}, signature)
    assert (await runtime.model_capabilities("mock-fast")).tool_calling == "unknown"
    assert not issued
    repeated = await core.verify_model("mock-fast", ctx, "tool-probe", mode="tool_calling")
    assert repeated == result and len(runtime.turns) == 2 and len(effects) == 1
    assert repeated.execution_evidence["capability_probe"]["expires_at"] == proof["expires_at"]
    assert await core.get_managed_result(result.run_id, ctx) == result
    assert (await core.get_managed_trace(result.run_id, ctx)).available
    with db.session() as session:
        row = session.get(RunStateModel, result.run_id)
        assert row.execution_mode == "tool_probe" and row.usage_settled and row.reserved_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["unknown_tool", "arguments", "extra_argument", "call_id", "two_calls",
    "text_only", "forged", "timeout", "model", "reported_model", "continuation", "output", "provider", "usage", "run_id", "iteration"])
async def test_capability_probe_invalid_observations_cannot_attest(lifecycle, monkeypatch, fault):
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    effects = []
    execute = fixture.execute
    def tracked(arguments, context):
        effects.append(context.run_id)
        return execute(arguments, context)
    monkeypatch.setattr(fixture, "execute", tracked)
    native = runtime.execute_tool_turn
    async def broken(turn, context):
        if fault == "timeout":
            raise TimeoutError()
        if fault == "continuation" and turn.iteration == 2:
            raise RuntimeError("Isolated continuation failure")
        result = await native(turn, context)
        if fault == "output":
            result.result.output = '{"summary":"unverified"}'
        if fault == "provider" and turn.iteration == 2:
            result.result.provider = "different-test-provider"
        if turn.iteration == 1:
            if fault == "unknown_tool":
                result.tool_calls[0].name = "terminal"
            if fault == "arguments":
                result.tool_calls[0].arguments = {"key": "another-key"}
            if fault == "extra_argument":
                result.tool_calls[0].arguments["host"] = "synthetic-only"
            if fault == "call_id":
                result.tool_calls[0] = ToolCall.model_construct(call_id="invalid identity", name=fixture.NAME, arguments={"key": "aryn-core"})
            if fault == "two_calls":
                result.tool_calls.append(result.tool_calls[0].model_copy(update={"call_id": "second"}))
            if fault == "text_only":
                result.tool_calls = []
                result.result.status = RunStatus.COMPLETED
            if fault == "forged":
                result.result.execution_evidence = {"run_id": turn.run_id}
            if fault == "model":
                result.result.actual_model = "another-model"
            if fault == "reported_model":
                result.result.reported_model = "another-model"
            if fault == "usage":
                result.result.usage = RunUsage()
            if fault == "run_id":
                result.run_id = "foreign-run"
            if fault == "iteration":
                result.iteration = 2
        return result
    runtime.execute_tool_turn = broken
    try:
        result = await core.verify_model("mock-fast", ctx, "invalid-probe", mode="tool_calling")
        assert result.status == RunStatus.FAILED
        assert "capability_attestation" not in (result.execution_evidence or {})
    except (PermissionDeniedError, ValueError, TimeoutError, ModelIdentityError, RuntimeError):
        pass
    assert len(effects) == (1 if fault in {"continuation", "output", "provider"} else 0)
    assert (await runtime.model_capabilities("mock-fast")).tool_calling == "unknown"
    with db.session() as session:
        assert session.query(RunStateModel).filter_by(execution_mode="tool_probe", status="completed").count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["viewer", "agent", "foreign", "expired", "revoked"])
async def test_capability_probe_requires_current_human_permission(lifecycle, boundary):
    from packages.contracts.core import ActorType
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    if boundary in {"viewer", "revoked"}:
        with db.session(write=True) as session:
            row = session.query(MembershipModel).filter_by(user_id=ctx.actor.actor_id).one()
            if boundary == "viewer":
                row.role = "viewer"
            else:
                row.status = "suspended"
    elif boundary == "agent":
        ctx = ctx.model_copy(deep=True)
        ctx.actor.actor_type = ActorType.AGENT
        ctx = bind_test_context(ctx)
    elif boundary == "foreign":
        ctx = bind_test_context(ctx.model_copy(update={"project_id": "foreign"}))
    else:
        ctx = core.permission_engine.identity_binder.bind_context(ctx, ttl_seconds=-1)
    with pytest.raises(PermissionDeniedError):
        await core.verify_model("mock-fast", ctx, "denied-probe", mode="tool_calling")
    assert not runtime.turns


@pytest.mark.asyncio
async def test_capability_probe_keeps_normal_agent_admission_and_probe_payload_closed(lifecycle):
    from packages.contracts.model import tool_probe_request
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    with pytest.raises(PermissionDeniedError):
        await core.verify_model("mock-fast", ctx, "invalid-mode", mode="arbitrary")
    with pytest.raises(PermissionDeniedError):
        await core.execute_managed_direct_turn(tool_probe_request("mock-fast", "direct-bypass"), ctx, _execution_mode="tool_probe")
    forged = tool_probe_request("mock-fast", "forged")
    forged.prompt = "Untrusted prompt"
    with pytest.raises(PermissionDeniedError):
        core._claim(forged, ctx, "tool_probe")
    assert not runtime.turns
    with db.session() as session:
        assert session.query(RunStateModel).count() == 0


@pytest.mark.asyncio
async def test_capability_probe_does_not_authorize_normal_unknown_agent(lifecycle):
    _, ctx, runtime, core, assignment, _ = await published(lifecycle)
    runtime.tool_capability = "unknown"
    runtime.turns.clear()
    assert (await core.verify_model("mock-fast", ctx, "probe-only", mode="tool_calling")).status == RunStatus.COMPLETED
    with pytest.raises(PermissionDeniedError):
        await core.execute_assigned_agent_turn(assignment.id, "Read aryn-core.", ctx, "ordinary-unknown")
    assert len(runtime.turns) == 2


@pytest.mark.asyncio
async def test_capability_probe_duplicate_and_stop_keep_owner_fencing(lifecycle, monkeypatch):
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    entered, release = asyncio.Event(), asyncio.Event()
    effects = []
    monkeypatch.setattr(fixture, "execute", lambda *args: effects.append(True))
    async def blocked(turn):
        entered.set()
        await release.wait()
    runtime.before_result = blocked
    task = asyncio.create_task(core.verify_model("mock-fast", ctx, "inflight-probe", mode="tool_calling"))
    await asyncio.wait_for(entered.wait(), 3)
    with pytest.raises(RunInProgressError):
        await core.verify_model("mock-fast", ctx, "inflight-probe", mode="tool_calling")
    with db.session() as session:
        run_id = session.query(RunStateModel).filter_by(execution_mode="tool_probe").one().id
    assert not await core.cancel_managed_run(run_id, ctx)
    release.set()
    with pytest.raises(PermissionDeniedError):
        await task
    assert not effects and len(runtime.turns) == 1
    with db.session() as session:
        row = session.get(RunStateModel, run_id)
        assert row.status == "outcome_unknown" and row.reserved_tokens > 0 and not row.usage_settled


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["tokens", "turns"])
async def test_capability_probe_reserves_budget_before_dispatch(lifecycle, limit):
    from modules.core.usage.engine import BudgetExceededError
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    with db.session(write=True) as session:
        for budget in BudgetRepository(session).authority_budgets(ctx):
            if limit == "tokens":
                budget.max_tokens_per_run = 20
            else:
                budget.max_turns = 1
    with pytest.raises(BudgetExceededError):
        await core.verify_model("mock-fast", ctx, "budget-probe", mode="tool_calling")
    assert not runtime.turns


@pytest.mark.asyncio
async def test_http_probe_unknown_candidate_and_forged_live_origin_stay_isolated(lifecycle):
    from packages.contracts.runtime import ToolTurnRequest, ModelUnavailableError
    from packages.contracts.model import ModelProbeBinding, ModelProviderType, ModelSpec
    from packages.model_adapters import ModelRouter
    from tests.gateway_fixtures import make_adapter, standard_handler, MODEL, BASE
    db, ctx, double, core = capability_probe_core(lifecycle)
    posts = []
    adapter = None
    async def handler(request):
        if request.url.port == 20128:
            return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL, "provider_configuration": "c" * 64}]})
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={"data": [], "governed_tool_turns": True, "tool_isolation": "read_only_fixture"})
        if request.url.path == "/aryn/gateway":
            return httpx.Response(200, json={"gateway": "9Router", "runtime_backend": "Hermes", "base_url": BASE,
                "exact_model_enforced": True, "runtime_instance": "a" * 32,
                "configuration_id": adapter.model_gateway.settings.runtime_configuration_id("a" * 32)})
        if request.url.path == "/aryn/turn":
            posts.append(request)
            turn = ToolTurnRequest.model_validate_json(request.content)
            result = await double.execute_tool_turn(turn, ctx)
            result.result.reported_model = MODEL
            result.result.model_evidence = ModelProbeBinding(origin="gateway_response",
                runtime_configuration=adapter.model_gateway.settings.runtime_configuration_id("a" * 32),
                gateway_configuration=adapter.model_gateway.settings.configuration_id, provider_configuration="c" * 64)
            return httpx.Response(200, json=result.model_dump(mode="json"))
        return standard_handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = make_adapter(client)
        core.runtime_adapter = adapter
        core.model_router = ModelRouter(catalog={MODEL: ModelSpec(provider=ModelProviderType.NINE_ROUTER,
            model_id=MODEL, display_name=MODEL, requires_api_key=False)})
        with pytest.raises(ModelUnavailableError):
            await adapter.require_model_available(MODEL)
        result = await core.verify_model(MODEL, ctx, "http-probe", mode="tool_calling")
        assert result.status == RunStatus.COMPLETED and len(posts) == 2
        proof = result.execution_evidence["capability_probe"]
        assert proof["binding"]["origin"] == "isolated_test_double"
        assert not adapter.model_gateway.record_tool_verification(proof,
            result.execution_evidence["capability_attestation"], db.evidence_signer)
        assert (await adapter.model_capabilities(MODEL)).tool_calling == "unknown"
        with pytest.raises(ModelUnavailableError):
            await adapter.require_model_available(MODEL)


def capability_receipt_policy_fixture(lifecycle):
    """Synthetic signed policy input, not evidence of executed model inference."""
    from packages.contracts.model import ModelProbeEvidence, ModelProbeBinding
    from packages.model_adapters.gateway import NineRouterGateway, GatewaySettings
    db = lifecycle[0]
    settings = GatewaySettings(base_url="http://127.0.0.1:9/v1", api_key="unit-scope")
    gateway = NineRouterGateway(settings)
    configuration = settings.runtime_configuration_id("a" * 32)
    gateway.bind_runtime_configuration(configuration)
    gateway._provider_configurations["test/model"] = "c" * 64
    gateway._provider_identities["test/model"] = "unit-provider"
    now = time.time()
    evidence = ModelProbeEvidence(run_id="run_" + "a" * 32, model="test/model", provider="unit-provider",
        reported_model="test/model", observed_at=now, expires_at=now + 60, tool_call_id="unit-call",
        transcript_hash="d" * 64, output_hash="e" * 64,
        binding=ModelProbeBinding(origin="gateway_response", runtime_configuration=configuration,
            gateway_configuration=settings.configuration_id, provider_configuration="c" * 64))
    return gateway, evidence, db.evidence_signer


def test_capability_receipt_policy_accepts_only_scoped_fresh_signed_inputs(lifecycle):
    gateway, evidence, signer = capability_receipt_policy_fixture(lifecycle)
    signature = signer.sign("model_capability_probe", evidence.model_dump(mode="json"))
    assert gateway.record_tool_verification(evidence, signature, signer)
    assert gateway._verified_tool_probe("test/model") == evidence
    assert gateway._verified_tool_probe("another/model") is None


@pytest.mark.parametrize("fault", ["signature", "expired", "future", "ttl", "gateway", "runtime",
    "provider_configuration", "missing_provider", "missing_configuration", "isolated", "reported_identity"])
def test_capability_receipt_policy_rejects_unverifiable_inputs(lifecycle, fault):
    gateway, evidence, signer = capability_receipt_policy_fixture(lifecycle)
    if fault == "expired":
        evidence = evidence.model_copy(update={"observed_at": time.time() - 61, "expires_at": time.time() - 1})
    if fault == "future":
        evidence = evidence.model_copy(update={"observed_at": time.time() + 30, "expires_at": time.time() + 60})
    if fault == "ttl":
        evidence = evidence.model_copy(update={"expires_at": time.time() + 120})
    if fault == "gateway":
        gateway.settings = gateway.settings.model_copy(update={"base_url": "http://127.0.0.1:10/v1"})
    if fault == "runtime":
        gateway.bind_runtime_configuration("f" * 64)
    if fault == "provider_configuration":
        gateway._provider_configurations[evidence.model] = "f" * 64
    if fault == "missing_provider":
        evidence = evidence.model_copy(update={"provider": None})
    if fault == "reported_identity":
        evidence = evidence.model_copy(update={"reported_model": "another/model"})
    if fault in {"missing_configuration", "isolated"}:
        evidence = evidence.model_copy(update={"binding": evidence.binding.model_copy(update={
            "provider_configuration": None} if fault == "missing_configuration" else {"origin": "isolated_test_double"})})
    signature = signer.sign("model_capability_probe", evidence.model_dump(mode="json")) if fault != "signature" else "forged"
    assert not gateway.record_tool_verification(evidence, signature, signer)
    assert gateway._verified_tool_probe(evidence.model) is None


def test_capability_receipt_replay_never_renews_expiry(lifecycle, monkeypatch):
    gateway, evidence, signer = capability_receipt_policy_fixture(lifecycle)
    signature = signer.sign("model_capability_probe", evidence.model_dump(mode="json"))
    assert gateway.record_tool_verification(evidence, signature, signer)
    monkeypatch.setattr(time, "time", lambda: evidence.expires_at + 1)
    assert not gateway.record_tool_verification(evidence, signature, signer)
    assert gateway._verified_tool_probe(evidence.model) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["unsupported", "revoked", "configuration"])
async def test_capability_probe_revalidates_before_effects(lifecycle, monkeypatch, boundary):
    from packages.contracts.model import ModelProbeBinding
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    effects = []
    monkeypatch.setattr(fixture, "execute", lambda *args: effects.append(True))
    if boundary == "unsupported":
        runtime.tool_capability = "unsupported"
    elif boundary == "revoked":
        async def revoke(turn):
            with db.session(write=True) as session:
                session.query(MembershipModel).filter_by(user_id=ctx.actor.actor_id).one().status = "revoked"
        runtime.before_result = revoke
    else:
        count = 0
        async def changed_binding():
            nonlocal count
            count += 1
            return ModelProbeBinding(origin="isolated_test_double", gateway_configuration="a" * 64,
                runtime_configuration=("b" if count == 1 else "c") * 64)
        runtime.capability_verification_binding = changed_binding
    with pytest.raises(PermissionDeniedError):
        await core.verify_model("mock-fast", ctx, "revalidate-probe", mode="tool_calling")
    assert not effects
    assert len(runtime.turns) <= 1


@pytest.mark.asyncio
async def test_expired_capability_cannot_survive_cached_availability(lifecycle, monkeypatch):
    from packages.contracts.runtime import GatewayDiscovery
    gateway, evidence, signer = capability_receipt_policy_fixture(lifecycle)
    signature = signer.sign("model_capability_probe", evidence.model_dump(mode="json"))
    assert gateway.record_tool_verification(evidence, signature, signer)
    snapshot = GatewayDiscovery(connected=True, discovery_valid=True, models=[{
        "model_id": evidence.model, "availability": "available", "availability_reason": "core_tool_probe_verified",
        "availability_source": "core_runtime_probe"}])
    async def cached(**kwargs):
        return snapshot
    gateway.discover = cached
    monkeypatch.setattr(time, "time", lambda: evidence.expires_at + 1)
    assert (await gateway.availability(evidence.model)).status == "unknown"


@pytest.mark.asyncio
async def test_capability_probe_permission_revoked_at_settlement_cannot_issue_receipt(lifecycle):
    db, ctx, runtime, core = capability_probe_core(lifecycle)
    complete = core._complete_dispatch
    def revoked(run_id, result, context):
        with db.session(write=True) as session:
            session.query(MembershipModel).filter_by(user_id=ctx.actor.actor_id).one().role = "viewer"
        return complete(run_id, result, context)
    core._complete_dispatch = revoked
    with pytest.raises(PermissionDeniedError):
        await core.verify_model("mock-fast", ctx, "settlement-revoked", mode="tool_calling")
    assert len(runtime.turns) == 2
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="settlement-revoked").one()
        assert row.status == "outcome_unknown" and row.reserved_tokens > 0 and not row.usage_settled
    events = core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx)
    assert not any(e.event_type == "core.run.evidence" for e in events)


@pytest.mark.asyncio
async def test_isolated_transport_cannot_reuse_cached_capability_receipt(lifecycle):
    from packages.runtime_adapters.hermes import HermesRuntimeAdapter
    gateway, evidence, signer = capability_receipt_policy_fixture(lifecycle)
    signature = signer.sign("model_capability_probe", evidence.model_dump(mode="json"))
    assert gateway.record_tool_verification(evidence, signature, signer)
    def handler(request):
        if request.url.path == "/aryn/gateway":
            return httpx.Response(200, json={"gateway": "9Router", "runtime_backend": "Hermes",
                "base_url": gateway.settings.base_url, "exact_model_enforced": True,
                "runtime_instance": "a" * 32, "configuration_id": evidence.binding.runtime_configuration})
        return httpx.Response(200, json={"object": "list", "data": [{"id": evidence.model,
            "provider_configuration": evidence.binding.provider_configuration}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway.client = client
        adapter = HermesRuntimeAdapter(api_key="isolated-runtime-auth", http_client=client, model_gateway=gateway)
        assert (await adapter.model_capabilities(evidence.model)).tool_calling == "unknown"
        assert not gateway.has_tool_verifications
