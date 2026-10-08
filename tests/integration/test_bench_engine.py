"""Generic suites exercise the existing Factory lifecycle, storage and API."""
from tests.integration.test_studio_api import studio as studio
import json
import pytest
from packages.contracts.bench import (
    ApprovalGraderSpec,
    ApprovalRequirement,
    EvaluationState,
    ForbiddenActionGraderSpec,
    IdempotencyGraderSpec,
    ResourceLimits,
    evidence_hash,
)
from database.repositories.bench_repo import BenchRepository
from modules.bench.quality_gate import QualityGateFailedError
from tests.bench_fixtures import generic_scenario, generic_suite, install_generic_suite, StructuredRuntime, create_generic_version


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
async def test_generic_suite_promotes_through_existing_factory(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    assert evaluation.passed and evaluation.total_scenarios == 2 and evaluation.evidence_format == 2
    assert evaluation.suite_aggregate.passed and evaluation.quality_gate.passed
    assert all(len(s.grader_results) == 5 and s.execution.attestation for s in evaluation.scenario_results)
    assert [r.metadata["scenario_id"] for r in runtime.requests] == ["summary", "extraction"]
    assert not any(g.type == "text_pattern" for s in generic_suite().scenarios for g in s.graders)
    with db.session() as session:
        repo = BenchRepository(session, db.evidence_signer)
        stored = repo.get_evaluation(ctx, evaluation.evaluation_id)
        assert repo.validate_stored(ctx, stored, version) == evaluation
        assert json.loads(stored.provenance_json)["suite_aggregate"]["total_scenarios"] == 2
    approval = factory.approve_version(ctx, version.id)
    assert approval.evaluation_id == evaluation.evaluation_id and approval.payload_hash == version.payload_hash
    assert factory.publish_version(ctx, version.id).status == "published"


@pytest.mark.asyncio
@pytest.mark.parametrize("output,state", [('{}', "failed"), ('malformed', "failed")])
async def test_generic_schema_failure_blocks_publication(lifecycle, monkeypatch, output, state):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, runtime=StructuredRuntime(output))
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed and result.state.value == state
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)
    with pytest.raises(QualityGateFailedError):
        factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
async def test_scenario_schema_cannot_weaken_agent_output_contract(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    # A new canonical version legitimately requires an additional field; the suite cannot override it.
    constrained = factory.create_version(ctx, bp.id, "3.0.0", "Return JSON with citations.", "mock-fast",
        evaluation_reference={"suite_id": "analysis"}, output_contract={"format":"json", "schema_definition":{
            "type":"object", "required":["citation"]}})
    result = await factory.evaluate_version_with_bench(ctx, constrained.id)
    assert not result.passed
    assert all(next(g for g in r.grader_results if g.grader_type == "schema_validity").reason == "output_schema_violation" for r in result.scenario_results)


@pytest.mark.asyncio
async def test_invalid_suite_definition_and_subset_rejected_before_dispatch(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    with pytest.raises(QualityGateFailedError):
        await factory.evaluate_version_with_bench(ctx, version.id, generic_suite().scenarios[:1])
    assert runtime.requests == []
    from modules.bench.registry import BenchSuiteRegistry
    suite = generic_suite()
    suite.scenarios[0].graders.clear()
    with pytest.raises(ValueError):
        BenchSuiteRegistry([suite])


@pytest.mark.asyncio
@pytest.mark.parametrize("observations,expected", [
    (None,"unverifiable"), ({"cost_usd":0.1,"resources":{"cpu_seconds":1}},"passed"),
    ({"cost_usd":2,"resources":{"cpu_seconds":1}},"failed"),
    ({"cost_usd":float("nan")},"invalid_evidence"), ({"cost_usd":True},"invalid_evidence"),
    ({"cost_usd":0.1,"resources":{"cpu_seconds":float("inf")}},"invalid_evidence"),
])
async def test_cost_and_resource_evidence_is_required_by_policy(lifecycle, monkeypatch, observations, expected):
    limits = ResourceLimits(max_cost_usd=1, max_resources={"cpu_seconds":2})
    suite = generic_suite(resource_limits=limits)
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite, StructuredRuntime(observations=observations))
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.state.value == expected and result.passed is (expected == "passed")
    if not result.passed:
        with pytest.raises(QualityGateFailedError):
            factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
async def test_runtime_error_is_distinct_from_failed_evaluation(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    async def unavailable(request, context): raise RuntimeError("untrusted-secret-body")
    runtime.execute_direct_turn = unavailable
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.state == EvaluationState.RUNTIME_ERROR and not result.passed
    assert "untrusted-secret-body" not in result.model_dump_json()
    with db.session() as s:
        stored = BenchRepository(s, db.evidence_signer).get_evaluation(ctx, result.evaluation_id)
        assert BenchRepository(s, db.evidence_signer).validate_stored(ctx, stored, version).state == EvaluationState.RUNTIME_ERROR


@pytest.mark.asyncio
async def test_action_trace_requirement_is_fail_closed_with_current_runtime(lifecycle, monkeypatch):
    scenario = generic_scenario(forbidden_actions=["send_message"])
    scenario.graders[2] = ForbiddenActionGraderSpec(grader_id="boundaries", evidence_mode="action_trace")
    suite = generic_suite(scenarios=[scenario], scenario_ids=[scenario.scenario_id])
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.state == EvaluationState.UNVERIFIABLE
    assert next(g for g in result.scenario_results[0].grader_results if g.grader_type == "forbidden_action").reason == "complete_action_trace_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("actions,state", [([], "passed"), ([{"action_id":"send","action":"send_message"}],"policy_violation")])
async def test_richer_action_evidence_is_graded(lifecycle, monkeypatch, actions, state):
    scenario = generic_scenario(forbidden_actions=["send_message"])
    suite = generic_suite(scenarios=[scenario], scenario_ids=[scenario.scenario_id])
    runtime = StructuredRuntime(observations={"trace_complete":True,"actions":actions})
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite, runtime)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.state.value == state


@pytest.mark.asyncio
async def test_core_approval_is_composable_in_generic_suite(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = lifecycle
    payload_hash = evidence_hash({"operation":"isolated_review"})
    approval = factory.approval_engine.grant_approval(ctx, "test_action", "operation", payload_hash)
    requirement = ApprovalRequirement(target_type="test_action", target_id="operation", payload_hash=payload_hash,
                                      allowed_actors=["owner"])
    scenario = generic_scenario()
    scenario.graders.append(ApprovalGraderSpec(grader_id="operation_approval", requirement=requirement))
    suite = generic_suite(scenarios=[scenario], scenario_ids=[scenario.scenario_id])
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.passed and result.scenario_results[0].grader_results[-1].reason == "core_approval_verified"
    # Revoking the existing Core record invalidates previously captured approval evidence.
    from database.schema import ApprovalModel
    with db.session() as s:
        s.get(ApprovalModel, approval.approval_id).status = "rejected"
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)


@pytest.mark.asyncio
async def test_idempotency_policy_without_observations_cannot_pass(lifecycle, monkeypatch):
    scenario = generic_scenario()
    scenario.graders.append(IdempotencyGraderSpec(grader_id="repeat", idempotency_key="operation",
                                                request_hash=evidence_hash({"request":1})))
    suite = generic_suite(scenarios=[scenario], scenario_ids=[scenario.scenario_id])
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.state == EvaluationState.UNVERIFIABLE
    assert result.scenario_results[0].grader_results[-1].reason == "idempotency_evidence_insufficient"


@pytest.mark.asyncio
async def test_suite_aggregate_and_stricter_promotion_gate_are_distinct(lifecycle, monkeypatch):
    suite = generic_suite(min_score_threshold=0.5, required_scenarios=["summary"])
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite)
    original = runtime.execute_direct_turn
    async def mixed(request, context):
        result = await original(request, context)
        if request.metadata["scenario_id"] == "extraction":
            result.output = '{}'
        return result
    runtime.execute_direct_turn = mixed
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.score == 0.5 and result.suite_aggregate.passed
    assert not result.quality_gate.passed and not result.passed
    with pytest.raises(QualityGateFailedError):
        factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
async def test_generic_api_preflight_and_completion_use_referenced_suite(studio, monkeypatch):
    from tests.integration.test_studio_api import draft, PREFIX
    client, db, runtime, app = studio
    install_generic_suite(monkeypatch)
    bp, original = draft(client)
    original_execute = runtime.execute_direct_turn
    async def structured(request, context):
        result = await original_execute(request, context)
        result.output = '{"summary":"ok"}'
        return result
    runtime.execute_direct_turn = structured
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json={
        "version_number":"2.0.0", "system_prompt":"Return grounded structured JSON output.", "model":original["model"],
        "evaluation_reference":{"suite_id":"analysis"}, "output_contract":{"format":"json"}})
    assert response.status_code == 201, response.text
    version = response.json()
    evaluated = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model":True})
    assert evaluated.status_code == 200, evaluated.text
    result = evaluated.json()
    assert result["total_scenarios"] == 2 and result["passed"] and result["evaluation"]["verified"]
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert next(s for s in snapshot["evaluation_suites"] if s["suite_id"] == "structured-analysis")["scenarios"][0]["scenario_id"] == "summary"


# Import existing API fixture without introducing another application path.
