"""Generic Bench promotion rejects forged aggregates, identities and evidence."""
import json
import pytest
from database.repositories.bench_repo import BenchRepository
from database.repositories.exceptions import TenantIsolationError
from database.schema import BenchEvaluationModel
from packages.contracts.bench import BenchEvaluationResult, ScenarioResult, EvaluationState
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from modules.bench.registry import BenchSuiteRegistry
from modules.bench import scenarios
from tests.bench_fixtures import generic_suite
from tests.bench_fixtures import create_generic_version


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["grader_pass", "grader_reason", "scenario_pass", "suite_score", "gate_threshold", "execution_output", "execution_signature", "runtime_adapter", "tenant"])
async def test_even_resigned_outer_aggregates_require_deterministic_evidence(lifecycle, monkeypatch, mutation):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    forged = result.model_copy(deep=True)
    if mutation == "grader_pass":
        grader = forged.scenario_results[0].grader_results[0]
        object.__setattr__(grader, "passed", False)
        object.__setattr__(grader, "state", EvaluationState.FAILED)
    if mutation == "grader_reason":
        forged.scenario_results[0].grader_results[0].reason = "runtime_claimed_pass"
    if mutation == "scenario_pass":
        forged.scenario_results[0].passed = False
    if mutation == "suite_score":
        forged.suite_aggregate.score = 0.5
    if mutation == "gate_threshold":
        forged.quality_gate.min_score_threshold = 0
    if mutation == "execution_output":
        forged.scenario_results[0].execution.output = '{"summary":"tampered"}'
    if mutation == "execution_signature":
        forged.scenario_results[0].execution.attestation = ""
    if mutation == "runtime_adapter":
        forged.runtime_adapter = "untrusted.adapter"
    if mutation == "tenant":
        forged.scenario_results[0].execution.project_id = "other"
    forged.attestation = db.evidence_signer.sign("bench", forged.evidence_payload(ctx.organization_id, ctx.project_id, ctx.actor.actor_id))
    with db.session() as session:
        with pytest.raises(QualityGateFailedError):
            BenchRepository(session, db.evidence_signer).verify_result(ctx, forged, version, ctx.actor.actor_id)


@pytest.mark.asyncio
async def test_generic_evidence_is_tenant_bound(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    foreign = ctx.model_copy(update={"project_id":"foreign"})
    with db.session() as session:
        repo = BenchRepository(session, db.evidence_signer)
        with pytest.raises(TenantIsolationError):
            repo.get_evaluation(foreign, result.evaluation_id)
        with pytest.raises(QualityGateFailedError):
            repo.verify_result(foreign, result, version, ctx.actor.actor_id)


@pytest.mark.asyncio
async def test_suite_configuration_change_invalidates_saved_evidence(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    await factory.evaluate_version_with_bench(ctx, version.id)
    research = scenarios.get_bench_suite("research-safety")
    suite = generic_suite()
    values = suite.model_dump(mode="json")
    values["suite_hash"] = ""
    values["scenarios"][0]["scenario_version"] = "1.1.0"
    changed = type(suite).model_validate(values)
    monkeypatch.setattr(scenarios, "BENCH_SUITE_REGISTRY", BenchSuiteRegistry([research, changed]))
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)
    with pytest.raises(QualityGateFailedError):
        factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
async def test_cross_suite_reference_cannot_match_by_research_alias(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    from packages.contracts.agent import AgentEvaluationReference
    with pytest.raises(QualityGateFailedError):
        BenchQualityGate().enforce(result, AgentEvaluationReference(), signer=db.evidence_signer)


@pytest.mark.asyncio
async def test_runtime_pass_boolean_cannot_override_evidence(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    original = runtime.execute_direct_turn
    async def boolean_claim(request, context):
        result = await original(request, context)
        result.execution_evidence = {"run_id":result.run_id,"passed":True,"score":1}
        return result
    runtime.execute_direct_turn = boolean_claim
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not evaluation.passed and evaluation.state == EvaluationState.INVALID_EVIDENCE
    with pytest.raises(QualityGateFailedError):
        factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["model","actual_model","requested_model"])
async def test_adapter_model_fallback_is_rejected(lifecycle, monkeypatch, field):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    original = runtime.execute_direct_turn
    async def fallback(request, context):
        result = await original(request, context)
        setattr(result, field, "silent-fallback")
        return result
    runtime.execute_direct_turn = fallback
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed and result.state == EvaluationState.POLICY_VIOLATION
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)


@pytest.mark.asyncio
async def test_research_historical_attestation_retains_original_serialization(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    current = await factory.evaluate_version_with_bench(ctx, version.id)
    legacy_fields = {"scenario_id","name","category","passed","score","actual_output","latency_seconds",
                     "failure_reason","actual_model","runtime_status","input_tokens","output_tokens","total_tokens"}
    legacy = BenchEvaluationResult(
        evaluation_id=current.evaluation_id, blueprint_id=current.blueprint_id, version_id=current.version_id,
        passed=current.passed, total_scenarios=4, passed_scenarios=4, score=1,
        scenario_results=[ScenarioResult(**r.model_dump(include=legacy_fields)) for r in current.scenario_results],
        suite_id=current.suite_id, evaluation_version=current.evaluation_version, payload_hash=current.payload_hash,
        suite_hash=scenarios.research_suite_hash(), runtime_adapter=current.runtime_adapter,
        requested_model=current.requested_model, evaluated_at=current.evaluated_at)
    payload = legacy.evidence_payload(ctx.organization_id, ctx.project_id, ctx.actor.actor_id)
    assert "evidence_format" not in payload["result"]
    assert "grader_results" not in payload["result"]["scenario_results"][0]
    legacy.attestation = db.evidence_signer.sign("bench", payload)
    with db.session() as session:
        row = session.get(BenchEvaluationModel, current.evaluation_id)
        row.details_json = json.dumps([r.model_dump(include=legacy_fields) for r in legacy.scenario_results])
        row.provenance_json = json.dumps({key: getattr(legacy,key) for key in (
            "suite_id","evaluation_version","requested_model","payload_hash","suite_hash","runtime_adapter","attestation","evaluated_at")})
    assert factory.approve_version(ctx, version.id).evaluation_id == legacy.evaluation_id
    assert factory.publish_version(ctx, version.id).status == "published"
    with db.session() as session:
        from database.repositories.bench_regression_repo import BenchRegressionRepository
        baseline = BenchRegressionRepository(session, db.evidence_signer).current(ctx, bp.id)
        assert baseline.evaluation.evidence_format == 1
        assert baseline.limitations == ["legacy_scenario_evidence_only", "grader_comparison_unavailable", "cost_resources_unavailable"]
        with pytest.raises(QualityGateFailedError):
            BenchRepository(session, db.evidence_signer).record_evaluation(ctx, legacy)
    # Current format cannot silently claim comparability with absent legacy graders.
    candidate = factory.create_version(ctx, bp.id, "2.0.0", "Follow research safety guidelines.", "mock-fast")
    current = await factory.evaluate_version_with_bench(ctx, candidate.id)
    with db.session() as session:
        comparison = BenchRegressionRepository(session, db.evidence_signer).compare(ctx, candidate.id)
        assert comparison.state == "incompatible" and comparison.promotion_blocked
        assert comparison.scenarios == []
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, candidate.id)
    with db.session(write=True) as session:
        replacement = BenchRegressionRepository(session, db.evidence_signer).accept(ctx, current.evaluation_id,
            expected_baseline_id=baseline.baseline_id, transition=True, reason="Human reviewed migration from historical scenario-only evidence to generic graders.")
        assert replacement.evaluation.evidence_format == 2 and not replacement.limitations
    factory.approve_version(ctx, candidate.id)
    assert factory.publish_version(ctx, candidate.id).status == "published"


@pytest.mark.asyncio
async def test_stored_tenant_columns_must_match_evaluation_context(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as session:
        repo = BenchRepository(session, db.evidence_signer)
        stored = repo.get_evaluation(ctx, result.evaluation_id)
        stored.project_id = "different-project"
        with pytest.raises(QualityGateFailedError):
            repo.validate_stored(ctx, stored, version)
        session.rollback()
