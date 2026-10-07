"""Positive and negative contracts for independently reusable deterministic graders."""
from dataclasses import replace
import datetime
import pytest
from pydantic import ValidationError
from packages.contracts.bench import (
    ActionEvidence,
    ApprovalGraderSpec,
    ApprovalRequirement,
    BenchScenario,
    EvaluationState,
    EvidenceFixture,
    EvidenceIntegrityGraderSpec,
    ForbiddenActionGraderSpec,
    IdempotencyGraderSpec,
    IdempotencyObservation,
    LatencyCostGraderSpec,
    ModelIdentityGraderSpec,
    OutputContract,
    RESEARCH_SAFETY_SUITE_ID,
    ResourceLimits,
    RuntimeRequirements,
    ScenarioExecutionEvidence,
    SchemaGraderSpec,
    evidence_hash,
)
from modules.bench.graders import (
    GradingContext, SchemaValidityGrader, ForbiddenActionGrader, ApprovalEnforcementGrader,
    IdempotencyGrader, ModelIdentityGrader, LatencyCostGrader, EvidenceIntegrityGrader, execute_graders,
)
from modules.bench.registry import BenchSuiteRegistry
from modules.bench.evidence import normalize_observations
from tests.bench_fixtures import generic_scenario, generic_suite, install_generic_suite


def grading_context(scenario=None, **changes):
    scenario = scenario or generic_scenario()
    values = dict(evaluation_id="evaluation", organization_id="org", project_id="project", version_id="version",
        payload_hash=evidence_hash({"version": 1}), suite_id="analysis", suite_hash=evidence_hash({"suite": 1}),
        scenario_id=scenario.scenario_id, scenario_version=scenario.scenario_version,
        scenario_hash=evidence_hash(scenario.model_dump(mode="json")), runtime_adapter="isolated.adapter",
        requested_model="exact/model", reported_model="exact/model", actual_model="exact/model",
        runtime_requested_model="exact/model", observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        run_id="runtime_run", runtime_status="completed", output='{"summary":"ok"}', latency_seconds=1,
        usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        capabilities={"tools_confined": True, "enabled_toolsets": [], "details": {}})
    values.update(changes)
    ev = ScenarioExecutionEvidence(**values)
    ev.execution_hash = evidence_hash(ev.integrity_payload())
    return GradingContext(scenario=scenario, execution=ev, evaluation_id=ev.evaluation_id, suite_id=ev.suite_id,
        suite_hash=ev.suite_hash, version_id=ev.version_id, payload_hash=ev.payload_hash,
        requested_model=ev.requested_model, runtime_adapter=ev.runtime_adapter,
        organization_id=ev.organization_id, project_id=ev.project_id)


def test_scenario_is_generic_typed_versioned_and_has_multiple_graders():
    scenario = generic_scenario()
    assert scenario.schema_version == "2.0.0" and scenario.category == "summarization"
    assert scenario.expected_pattern is None
    results = execute_graders(grading_context(scenario))
    assert len(results) == 5 and all(result.passed for result in results)
    assert BenchScenario.model_validate_json(scenario.model_dump_json()) == scenario


@pytest.mark.parametrize("changes", [
    {"prompt": ""}, {"scenario_id": ""}, {"scenario_version": "unknown"}, {"graders": []},
    {"graders": [{"grader_id": "unknown", "type": "runtime_boolean"}]},
    {"allowed_tools": ["shell"]}, {"allowed_actions": ["write"], "forbidden_actions": ["write"]}, {"forbidden_actions": [""]},
    {"resource_limits": {"max_latency_seconds": float("nan")}},
    {"evaluation_contract": {"format": "json", "schema_definition": {"type": "invalid"}}},
    {"evaluation_contract": {"format": "json", "schema_definition": {"$ref": "https://invalid/schema"}}},
    {"evaluation_contract": {"format": "json", "schema_definition": {"$ref": "#/$defs/missing"}}},
    {"unexpected_regex_field": "pass"},
])
def test_invalid_scenario_rejected(changes):
    with pytest.raises((ValueError, ValidationError)):
        generic_scenario(**changes)


def test_duplicate_grader_and_tool_identities_rejected():
    scenario = generic_scenario()
    with pytest.raises(ValueError):
        generic_scenario(graders=scenario.graders + [scenario.graders[0]])
    with pytest.raises(ValueError):
        generic_scenario(allowed_capabilities=["lookup", "lookup"])


def test_fixture_hash_validation():
    fixture = EvidenceFixture(fixture_id="source", payload={"value": 1}, payload_hash=evidence_hash({"value": 1}))
    assert generic_scenario(fixtures=[fixture]).fixtures == [fixture]
    with pytest.raises(ValueError):
        EvidenceFixture(fixture_id="source", payload={"value": 2}, payload_hash=fixture.payload_hash)


def test_registry_alias_resolution_is_immutable_and_rejects_collisions(monkeypatch):
    suite = generic_suite()
    registry = BenchSuiteRegistry([suite])
    resolved = registry.resolve("analysis")
    assert resolved.suite_id == suite.suite_id and registry.resolve("unknown") is None
    resolved.scenarios[0].prompt = "Modified in caller"
    assert registry.resolve("analysis").scenarios[0].prompt != resolved.scenarios[0].prompt
    with pytest.raises(ValueError):
        BenchSuiteRegistry([suite, suite])
    with pytest.raises(ValueError):
        other = generic_suite(suite_id="other", aliases=["analysis"])
        BenchSuiteRegistry([suite, other])
    install_generic_suite(monkeypatch)
    from packages.contracts.agent import AgentEvaluationReference
    reference = AgentEvaluationReference(suite_id="analysis")
    assert reference.evaluation_version == "2.1.0" and reference.required_scenarios == ["summary", "extraction"]
    assert AgentEvaluationReference().suite_id == RESEARCH_SAFETY_SUITE_ID


@pytest.mark.parametrize("output,strict,passed,reason", [
    ('{"summary":"ok"}', True, True, "output_contract_satisfied"),
    ('{"summary":"ok","extra":1}', False, True, "output_contract_satisfied"),
    ('{"summary":"ok","extra":1}', True, False, "output_schema_violation"),
    ('{}', False, False, "output_schema_violation"),
    ('{"summary":123}', False, False, "output_schema_violation"),
    ('not json', False, False, "malformed_structured_output"),
    ('{"summary":NaN}', False, False, "malformed_structured_output"),
    ('{"summary":"ok","summary":"other"}', False, False, "malformed_structured_output"),
])
def test_schema_validity(output, strict, passed, reason):
    scenario = generic_scenario()
    scenario.evaluation_contract.strict = strict
    result = SchemaValidityGrader().grade(SchemaGraderSpec(grader_id="schema"), grading_context(scenario, output=output))
    assert result.passed is passed and result.reason == reason


def test_schema_required_sections_and_missing_contract():
    scenario = generic_scenario(evaluation_contract=OutputContract(format="markdown", required_sections=["Evidence"]))
    assert not SchemaValidityGrader().grade(SchemaGraderSpec(grader_id="schema"), grading_context(scenario, output="Summary")).passed
    scenario = generic_scenario(evaluation_contract=None)
    result = SchemaValidityGrader().grade(SchemaGraderSpec(grader_id="schema"), grading_context(scenario))
    assert result.state == EvaluationState.UNVERIFIABLE


@pytest.mark.parametrize("changes,mode,state,reason", [
    ({}, "confinement", "passed", "adapter_confinement_verified"),
    ({"capabilities": None}, "confinement", "unverifiable", "capabilities_unavailable"),
    ({"capabilities": {"tools_confined": False, "enabled_toolsets": ["shell"]}}, "confinement", "policy_violation", "tool_boundary_violation"),
    ({}, "action_trace", "unverifiable", "complete_action_trace_unavailable"),
    ({"trace_available": True}, "action_trace", "passed", "action_boundary_verified"),
    ({"trace_error": "malformed"}, "action_trace", "invalid_evidence", "action_trace_malformed"),
    ({"trace_available": True, "actions": [{"action_id": "action", "action": "run", "tool": "shell"}]}, "action_trace", "policy_violation", "forbidden_action_observed"),
])
def test_forbidden_action(changes, mode, state, reason):
    result = ForbiddenActionGrader().grade(ForbiddenActionGraderSpec(grader_id="boundary", evidence_mode=mode), grading_context(**changes))
    assert result.state.value == state and result.reason == reason


def test_explicit_tool_and_capability_grants_are_required_even_with_complete_trace():
    scenario = generic_scenario(allowed_actions=["lookup"], allowed_tools=["lookup"], allowed_capabilities=["read"],
                               runtime_requirements=RuntimeRequirements(write_isolation="mocked"))
    ctx = grading_context(scenario, trace_available=True, actions=[ActionEvidence(action_id="lookup", action="lookup", tool="lookup", capability="read")],
        capabilities={"tools_confined": True, "enabled_toolsets": ["lookup"], "details": {"write_isolation": "mocked"}})
    spec = ForbiddenActionGraderSpec(grader_id="boundary", evidence_mode="action_trace")
    assert not ForbiddenActionGrader().grade(spec, ctx).passed
    ctx = replace(ctx, agent_tool_grants=("lookup",))
    assert ForbiddenActionGrader().grade(spec, ctx).passed
    ctx.execution.actions[0].capability = "write"
    assert ForbiddenActionGrader().grade(spec, ctx).state == EvaluationState.POLICY_VIOLATION


@pytest.mark.parametrize("changes,state,reason", [
    ({}, "passed", "exact_model_verified"),
    ({"reported_model": "other"}, "policy_violation", "model_identity_mismatch"),
    ({"actual_model": "fallback"}, "policy_violation", "model_identity_mismatch"),
    ({"runtime_requested_model": "other"}, "policy_violation", "model_identity_mismatch"),
    ({"reported_model": ""}, "unverifiable", "model_identity_missing"),
])
def test_model_identity(changes, state, reason):
    result = ModelIdentityGrader().grade(ModelIdentityGraderSpec(grader_id="model"), grading_context(**changes))
    assert result.state.value == state and result.reason == reason


@pytest.mark.parametrize("actual,expected,state", [(None,"provider","unverifiable"), ("other","provider","policy_violation"), ("provider","provider","passed")])
def test_model_provider_provenance(actual, expected, state):
    spec = ModelIdentityGraderSpec(grader_id="model", provider=expected)
    assert ModelIdentityGrader().grade(spec, grading_context(provider=actual)).state.value == state


@pytest.mark.parametrize("changes,limits,state,reason", [
    ({}, {"max_latency_seconds": 2}, "passed", "resource_limits_satisfied"),
    ({"latency_seconds": 6}, {}, "failed", "latency_limit_exceeded"),
    ({}, {"max_total_tokens": 4}, "failed", "token_limit_exceeded"),
    ({"usage": None}, {}, "unverifiable", "token_usage_unavailable"),
    ({"usage": {"input_tokens": 2,"output_tokens": 3,"total_tokens": 9}}, {}, "invalid_evidence", "token_usage_invalid"),
    ({"usage": {"input_tokens": True,"output_tokens": 3,"total_tokens": 4}}, {}, "invalid_evidence", "token_usage_invalid"),
    ({}, {"max_cost_usd": 1}, "unverifiable", "cost_unavailable"),
    ({"cost_usd": 0.3}, {"max_cost_usd": 1}, "passed", "resource_limits_satisfied"),
    ({"cost_usd": 2}, {"max_cost_usd": 1}, "failed", "cost_limit_exceeded"),
    ({}, {"max_resources": {"memory_mb": 100}}, "unverifiable", "resource_unavailable"),
    ({"resources": {"memory_mb": 10}}, {"max_resources": {"memory_mb": 100}}, "passed", "resource_limits_satisfied"),
    ({"resources": {"memory_mb": 101}}, {"max_resources": {"memory_mb": 100}}, "failed", "resource_limit_exceeded"),
])
def test_latency_cost_resources(changes, limits, state, reason):
    spec = LatencyCostGraderSpec(grader_id="resources", limits=ResourceLimits(**limits))
    result = LatencyCostGrader().grade(spec, grading_context(**changes))
    assert result.state.value == state and result.reason == reason


@pytest.mark.parametrize("field,value", [("latency_seconds", float("nan")), ("cost_usd", float("inf")), ("cost_usd", -1), ("resources", {"cpu": float("nan")})])
def test_non_finite_or_negative_resource_evidence_fails_closed(field, value):
    ctx = grading_context()
    ev = ctx.execution.model_copy(update={field: value})
    result = LatencyCostGrader().grade(LatencyCostGraderSpec(grader_id="resources"), replace(ctx, execution=ev))
    assert not result.passed and result.state == EvaluationState.INVALID_EVIDENCE


def observations():
    first = IdempotencyObservation(organization_id="org", project_id="project", idempotency_key="key",
        request_hash=evidence_hash({"request": 1}), result_hash=evidence_hash({"result": 1}),
        state_hash=evidence_hash({"state": 1}), side_effect_ids=["effect"], emitted_side_effect_ids=["effect"], replayed=False)
    return [first, first.model_copy(deep=True, update={"replayed": True, "emitted_side_effect_ids": []})]


@pytest.mark.parametrize("case,reason", [("valid","idempotency_observations_consistent"), ("missing","idempotency_evidence_insufficient"),
    ("duplicate","duplicate_side_effect"), ("repeated_effect","duplicate_side_effect"), ("identity","idempotency_identity_mismatch"), ("tenant","idempotency_identity_mismatch"),
    ("state","idempotency_state_mismatch"), ("execution","duplicate_execution_observed")])
def test_idempotency(case, reason):
    evidence = observations()
    if case == "missing": evidence = evidence[:1]
    if case == "duplicate": evidence[1].side_effect_ids.append("duplicate_effect")
    if case == "repeated_effect": evidence[1].emitted_side_effect_ids = ["effect"]
    if case == "identity": evidence[1].idempotency_key = "other"
    if case == "tenant": evidence[1].project_id = "foreign"
    if case == "state": evidence[1].state_hash = evidence_hash({"changed": True})
    if case == "execution": evidence[1].replayed = False
    spec = IdempotencyGraderSpec(grader_id="idempotency", idempotency_key="key", request_hash=evidence_hash({"request": 1}))
    result = IdempotencyGrader().grade(spec, grading_context(idempotency_observations=evidence))
    assert result.reason == reason and result.passed is (case == "valid")


@pytest.mark.parametrize("field,value", [("output","tampered"), ("suite_hash","other"), ("scenario_version","9.0.0"),
    ("runtime_adapter","different.adapter"), ("evaluation_id","foreign"), ("payload_hash","changed")])
def test_evidence_integrity_tampering(field, value):
    ctx = grading_context()
    assert EvidenceIntegrityGrader().grade(EvidenceIntegrityGraderSpec(grader_id="integrity"), ctx).passed
    setattr(ctx.execution, field, value)
    assert not EvidenceIntegrityGrader().grade(EvidenceIntegrityGraderSpec(grader_id="integrity"), ctx).passed


def test_evidence_attestation_required_when_present():
    from modules.core.evidence import EvidenceSigner
    signer = EvidenceSigner(b"isolated-evidence-signing-key-32-bytes")
    ctx = grading_context()
    ctx.execution.attestation = signer.sign("bench_execution", ctx.execution.integrity_payload())
    spec = EvidenceIntegrityGraderSpec(grader_id="integrity")
    assert EvidenceIntegrityGrader().grade(spec, ctx).state == EvaluationState.UNVERIFIABLE
    assert EvidenceIntegrityGrader().grade(spec, replace(ctx, signer=signer)).passed
    ctx.execution.attestation = "tampered"
    assert not EvidenceIntegrityGrader().grade(spec, replace(ctx, signer=signer)).passed


@pytest.mark.parametrize("case,reason", [("valid","core_approval_verified"), ("missing","approval_missing"),
    ("stale","approval_stale"), ("hash","approval_binding_mismatch"), ("target","approval_binding_mismatch"),
    ("actor","approval_actor_mismatch"), ("evaluation","approval_binding_mismatch"), ("unsigned","core_approval_verification_failed")])
def test_approval_uses_core_authority(lifecycle, case, reason):
    db, security, runtime, factory, bp, version = lifecycle
    payload_hash = evidence_hash({"operation": "isolated_review"})
    record = factory.approval_engine.grant_approval(security, "test_action", "operation", payload_hash)
    requirement = ApprovalRequirement(target_type="test_action", target_id="operation", payload_hash=payload_hash,
                                      allowed_actors=["owner"])
    records = [record.model_dump(mode="json")]
    if case == "missing": records = []

    if case == "hash": records[0]["payload_hash"] = evidence_hash({"changed": True})
    if case == "target": records[0]["target_id"] = "other"
    if case == "actor": requirement.allowed_actors = ["other"]
    if case == "evaluation": requirement.evaluation_id = "other"
    if case == "unsigned": records[0]["attestation"] = ""
    observed_at = datetime.datetime.now(datetime.timezone.utc)
    if case == "stale": observed_at += datetime.timedelta(days=1)
    ctx = grading_context(approval_records=records, observed_at=observed_at.isoformat())
    ctx = replace(ctx, approval_authority=factory.approval_engine)
    result = ApprovalEnforcementGrader().grade(ApprovalGraderSpec(grader_id="approval", requirement=requirement), ctx)
    assert result.reason == reason and result.passed is (case == "valid")


@pytest.mark.asyncio
async def test_core_idempotency_claim_observations_are_reusable(lifecycle):
    from modules.core.workflows.coordinator import RunCoordinator
    from database.repositories.run_state_repo import RunStateRepository
    from packages.contracts.runtime import RunRequest
    db, security, runtime, factory, bp, version = lifecycle
    coordinator = RunCoordinator(runtime, db_manager=db)
    request = RunRequest(prompt="Readonly research summary", model="mock-fast", idempotency_key="research-operation")
    evidence = []
    for index in range(2):
        result = await coordinator.execute_managed_direct_turn(request, security)
        with db.session() as session:
            row = RunStateRepository(session).get_run_by_idempotency_key(security, request.idempotency_key)
            state = {"run_id": row.id, "status": row.status, "output": row.output, "request_hash": row.request_hash}
            evidence.append(IdempotencyObservation(
                organization_id=security.organization_id, project_id=security.project_id,
                idempotency_key=request.idempotency_key, request_hash=row.request_hash,
                result_hash=evidence_hash({"output": result.output, "model": result.model, "status": result.status.value}),
                state_hash=evidence_hash(state), side_effect_ids=[], emitted_side_effect_ids=[], replayed=index > 0))
    assert len(runtime.requests) == 1
    spec = IdempotencyGraderSpec(grader_id="idempotency", idempotency_key=request.idempotency_key,
                                request_hash=evidence[0].request_hash)
    assert IdempotencyGrader().grade(spec, grading_context(idempotency_observations=evidence)).passed


def test_ungranted_action_with_no_tool_or_capability_is_denied():
    ctx = grading_context(trace_available=True, actions=[ActionEvidence(action_id="write", action="write", side_effect_id="effect")])
    spec = ForbiddenActionGraderSpec(grader_id="boundary", evidence_mode="action_trace")
    result = ForbiddenActionGrader().grade(spec, ctx)
    assert result.state == EvaluationState.POLICY_VIOLATION and result.reason == "forbidden_action_observed"
