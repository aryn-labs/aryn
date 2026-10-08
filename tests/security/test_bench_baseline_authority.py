"""Negative evidence, tenant, actor, and alternate promotion path coverage."""
import json
import pytest
from sqlalchemy import text

from database.repositories.bench_regression_repo import BenchRegressionRepository, RegressionGateFailedError
from database.repositories.bench_repo import BenchRepository
from database.repositories.exceptions import TenantIsolationError
from database.schema import AgentBlueprintModel, BenchBaselineModel, BenchComparisonModel
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.permissions.engine import PermissionDeniedError
from packages.contracts.core import ActorType
from packages.contracts.bench import ForbiddenActionGraderSpec
from tests.bench_fixtures import generic_suite, generic_scenario, create_generic_version, StructuredRuntime
from tests.conftest import bind_test_context
from tests.integration.test_bench_baseline_regression import accepted, candidate
from tests.storage_attacks import corrupt_storage


@pytest.mark.asyncio
async def test_failed_evaluation_cannot_become_accepted_baseline(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, runtime=StructuredRuntime("malformed"))
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed
    with db.session(write=True) as s:
        with pytest.raises(QualityGateFailedError):
            BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id, reason="Reject failed baseline.")
        s.rollback()
    with db.session() as s:
        assert s.query(BenchBaselineModel).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("column,value", [("score", "0.1"), ("passed", "0"), ("provenance_json", "'{}'"), ("details_json", "'[]'")])
async def test_tampered_evaluation_never_becomes_baseline(lifecycle, monkeypatch, column, value):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        s.execute(text(f"UPDATE bench_evaluations SET {column}={value} WHERE id=:id"), {"id": result.evaluation_id})
    with db.session(write=True) as s:
        with pytest.raises(QualityGateFailedError):
            BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id, reason="Reject tampered baseline.")
        s.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["organization", "project", "blueprint"])
async def test_baseline_scope_is_enforced(lifecycle, monkeypatch, boundary):
    db, ctx, runtime, factory, bp, version, evaluation, baseline = await accepted(lifecycle, monkeypatch)
    foreign = ctx.model_copy(deep=True)
    if boundary == "organization":
        foreign.organization_id = foreign.actor.organization_id = "another-org"
    elif boundary == "project": foreign.project_id = "another-project"
    with db.session() as s:
        repo = BenchRegressionRepository(s, db.evidence_signer)
        with pytest.raises(TenantIsolationError):
            repo.receipt(foreign, baseline.baseline_id, "another-blueprint" if boundary == "blueprint" else None)
        if boundary != "blueprint":
            with pytest.raises(TenantIsolationError): repo.verify_current_comparison(foreign, repo.compare(ctx, version.id).comparison_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_type", [ActorType.AGENT, ActorType.SYSTEM])
async def test_baseline_acceptance_cannot_be_performed_by_non_human(lifecycle, monkeypatch, actor_type):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    forged = ctx.model_copy(deep=True)
    forged.actor.actor_type = actor_type
    bind_test_context(forged)
    with db.session(write=True) as s:
        with pytest.raises(PermissionDeniedError):
            BenchRegressionRepository(s, db.evidence_signer).accept(forged, result.evaluation_id, reason="No self-acceptance.")
        s.rollback()


@pytest.mark.asyncio
async def test_baseline_acceptance_requires_current_admin_authority(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        s.execute(text("UPDATE memberships SET role='operator' WHERE user_id='owner'"))
    with db.session(write=True) as s:
        with pytest.raises(PermissionDeniedError):
            BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id, reason="Admin authority required.")
        s.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["baseline", "baseline_evaluation", "baseline_configuration", "comparison"])
async def test_governance_evidence_tampering_blocks_promotion(lifecycle, monkeypatch, target):
    db, ctx, runtime, factory, bp, version, prior, baseline = await accepted(lifecycle, monkeypatch)
    next_version = candidate(factory, ctx, bp)
    result = await factory.evaluate_version_with_bench(ctx, next_version.id)
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
    with corrupt_storage(db.engine) as s:
        if target == "baseline":
            s.execute(text("UPDATE bench_baselines SET accepted_by='forged' WHERE id=:id"), {"id": baseline.baseline_id})
        elif target == "baseline_evaluation":
            s.execute(text("UPDATE bench_evaluations SET score=0 WHERE id=:id"), {"id": prior.evaluation_id})
        elif target == "baseline_configuration":
            s.execute(text("UPDATE agent_versions SET system_prompt='tampered' WHERE id=:id"), {"id": version.id})
        else:
            s.execute(text("UPDATE bench_comparisons SET attestation='forged' WHERE id=:id"), {"id": comparison.comparison_id})
    with pytest.raises(QualityGateFailedError): factory.approve_version(ctx, next_version.id)
    with pytest.raises(QualityGateFailedError): factory.publish_version(ctx, next_version.id)
    with pytest.raises(QualityGateFailedError):
        factory.approval_engine.grant_approval(ctx, "agent_version", next_version.id, next_version.payload_hash)


@pytest.mark.asyncio
async def test_removing_current_baseline_pointer_does_not_restore_bootstrap(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, prior, baseline = await accepted(lifecycle, monkeypatch)
    next_version = candidate(factory, ctx, bp)
    await factory.evaluate_version_with_bench(ctx, next_version.id)
    with db.session() as s:
        s.execute(text("UPDATE agent_blueprints SET bench_baseline_id=NULL WHERE id=:id"), {"id": bp.id})
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
        assert comparison.state == "invalid" and comparison.reason == "baseline_integrity_invalid"
    with pytest.raises(RegressionGateFailedError): factory.approve_version(ctx, next_version.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["policy_violation", "invalid_evidence", "unverifiable", "runtime_error"])
async def test_new_unsafe_signed_scenario_failure_is_durable_and_critical(lifecycle, monkeypatch, state):
    suite = generic_suite()
    runtime = StructuredRuntime(observations={"trace_complete": True, "actions": []})
    if state == "unverifiable":
        definitions = []
        for scenario in suite.scenarios:
            definitions.append(generic_scenario(scenario_id=scenario.scenario_id, name=scenario.name, category=scenario.category,
                graders=[ForbiddenActionGraderSpec(grader_id="boundaries", evidence_mode="action_trace") if g.type == "forbidden_action" else g
                    for g in scenario.graders]))
        suite = generic_suite(scenarios=definitions)
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch, suite, runtime)
    prior = await factory.evaluate_version_with_bench(ctx, version.id)
    assert prior.passed
    with db.session(write=True) as s:
        baseline = BenchRegressionRepository(s, db.evidence_signer).accept(ctx, prior.evaluation_id, reason="Verified safe baseline.")
    next_version = candidate(factory, ctx, bp)
    original = runtime.execute_direct_turn
    async def unsafe(request, context):
        if state == "runtime_error": raise RuntimeError("Isolated execution failure")
        result = await original(request, context)
        if state == "policy_violation": result.actual_model = "silent-fallback"
        elif state == "invalid_evidence": result.execution_evidence = {"run_id": result.run_id, "passed": True}
        else: result.execution_evidence = None
        return result
    runtime.execute_direct_turn = unsafe
    result = await factory.evaluate_version_with_bench(ctx, next_version.id)
    assert not result.passed and result.state == state
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
        assert comparison.promotion_blocked
        assert any(r.kind == "scenario" and r.candidate_state == state and r.critical for r in comparison.regressions)
        assert s.get(BenchComparisonModel, comparison.comparison_id).attestation
    with pytest.raises(QualityGateFailedError): factory.approve_version(ctx, next_version.id)
    with pytest.raises(QualityGateFailedError): factory.publish_version(ctx, next_version.id)


@pytest.mark.asyncio
async def test_baseline_and_comparison_records_cannot_be_rewritten_by_orm(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, prior, baseline = await accepted(lifecycle, monkeypatch)
    with db.session() as s:
        row = s.get(BenchBaselineModel, baseline.baseline_id)
        row.accepted_by = "another-actor"
        with pytest.raises(ValueError, match="append-only"): s.flush()
        s.rollback()
    with db.session() as s:
        comparison = s.query(BenchComparisonModel).first()
        comparison.attestation = "edited"
        with pytest.raises(ValueError, match="append-only"): s.flush()
        s.rollback()


@pytest.mark.asyncio
async def test_historical_approval_serialization_remains_readable_for_published_sources(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    approval = factory.approve_version(ctx, version.id)
    from database.schema import ApprovalModel
    with db.session() as s:
        row = s.get(ApprovalModel, approval.approval_id)
        row.regression_comparison_id = None
        record = factory.approval_engine.contract(row)
        payload = record.model_dump(mode="json", exclude={"attestation", "regression_comparison_id"})
        row.attestation = db.evidence_signer.sign("human_approval", payload)
        s.execute(text("UPDATE agent_versions SET status='published', published_at=CURRENT_TIMESTAMP WHERE id=:id"), {"id": version.id})
    assert factory.approval_engine.verify_approval(ctx, "agent_version", version.id, version.payload_hash).regression_comparison_id is None
    with db.session(write=True) as s:
        baseline = BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id,
            reason="Admin adopted verified publication with historical Core approval serialization.")
        assert baseline.evaluation.version_id == version.id
