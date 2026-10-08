"""Accepted evaluation history enforces promotion through existing Core authority."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from sqlalchemy import text

from database.repositories.bench_regression_repo import BenchRegressionRepository, RegressionGateFailedError
from database.schema import BenchBaselineModel, AgentBlueprintModel
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.approvals.engine import ApprovalRequiredError
from packages.contracts.bench import RegressionPolicy
from packages.contracts.runtime import RunUsage
from tests.bench_fixtures import create_generic_version, generic_suite, install_generic_suite, StructuredRuntime


class SelectiveRuntime(StructuredRuntime):
    failing_scenario = None
    latency = 0.01
    tokens = 50
    async def execute_direct_turn(self, request, context):
        result = await super().execute_direct_turn(request, context)
        if request.metadata["scenario_id"] == self.failing_scenario:
            result.output = "{}"
        await asyncio.sleep(self.latency)
        result.usage = RunUsage(input_tokens=20, output_tokens=self.tokens - 20, total_tokens=self.tokens)
        return result


def candidate(factory, ctx, bp, number="3.0.0", required=None, threshold=1):
    return factory.create_version(ctx, bp.id, number, "Produce grounded structured JSON.", "mock-fast",
        evaluation_reference={"suite_id": "analysis", "required_scenarios": required if required is not None else ["summary", "extraction"],
            "min_score_threshold": threshold}, output_contract={"format": "json", "schema_definition": {"type": "object"}})


async def accepted(lifecycle, monkeypatch, suite=None):
    values = create_generic_version(lifecycle, monkeypatch, suite=suite, runtime=SelectiveRuntime())
    db, ctx, runtime, factory, bp, version = values
    if suite and suite.required_scenarios != suite.scenario_ids:
        version = candidate(factory, ctx, bp, "2.1.0", required=suite.required_scenarios, threshold=suite.min_score_threshold)
        values = (db, ctx, runtime, factory, bp, version)
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session(write=True) as session:
        baseline = BenchRegressionRepository(session, db.evidence_signer).accept(ctx, evaluation.evaluation_id,
            reason="Admin reviewed verified evaluation evidence.")
    return (*values, evaluation, baseline)


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
async def test_verified_evaluation_accepts_baseline_without_rewriting_signed_payload(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    from database.schema import BenchEvaluationModel
    with db.session() as s:
        before = s.get(BenchEvaluationModel, evaluation.evaluation_id).provenance_json
    with db.session(write=True) as s:
        repo = BenchRegressionRepository(s, db.evidence_signer)
        baseline = repo.accept(ctx, evaluation.evaluation_id, reason="Reviewed baseline.")
        assert repo.current(ctx, bp.id) == baseline
        assert baseline.suite_id == "structured-analysis" and baseline.generation == 1
        assert baseline.evaluation.payload_hash == version.payload_hash
    with db.session() as s:
        assert s.get(BenchEvaluationModel, evaluation.evaluation_id).provenance_json == before
        assert s.get(AgentBlueprintModel, bp.id).bench_baseline_id == baseline.baseline_id
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
async def test_first_publication_bootstraps_then_non_regressing_candidate_advances_history(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, version.id)
        assert comparison.state == "bootstrap" and not comparison.promotion_blocked
    approval = factory.approve_version(ctx, version.id)
    assert approval.regression_comparison_id == comparison.comparison_id
    factory.publish_version(ctx, version.id)
    next_version = candidate(factory, ctx, bp)
    await factory.evaluate_version_with_bench(ctx, next_version.id)
    with db.session() as s:
        repo = BenchRegressionRepository(s, db.evidence_signer)
        first = repo.current(ctx, bp.id)
        comparison = repo.compare(ctx, next_version.id)
        assert comparison.baseline_id == first.baseline_id and comparison.baseline.evaluation_id == evaluation.evaluation_id
        assert comparison.state == "comparable" and not comparison.promotion_blocked
    factory.approve_version(ctx, next_version.id)
    factory.publish_version(ctx, next_version.id)
    with db.session() as s:
        repo = BenchRegressionRepository(s, db.evidence_signer)
        second = repo.current(ctx, bp.id)
        assert second.generation == 2 and second.supersedes_id == first.baseline_id
        assert s.query(BenchBaselineModel).count() == 2
    # Republish is idempotent; older published assignment authority stays intact.
    factory.publish_version(ctx, version.id)
    factory.assign_agent(ctx, bp.id, version.id, "Older approved agent")
    with db.session() as s:
        assert s.query(BenchBaselineModel).count() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("critical", [False, True])
async def test_passing_aggregate_cannot_hide_required_or_policy_critical_regression(lifecycle, monkeypatch, critical):
    suite = generic_suite(required_scenarios=["summary"], min_score_threshold=0.5,
        regression_policy=RegressionPolicy(critical_scenarios=["extraction"]) if critical else None)
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch, suite)
    next_version = candidate(factory, ctx, bp, required=["summary"], threshold=0.5)
    runtime.failing_scenario = "extraction"
    result = await factory.evaluate_version_with_bench(ctx, next_version.id)
    assert result.passed and result.score == 0.5  # quality gate legitimately permits this optional failure
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
        assert comparison.score_delta == -0.5
        assert comparison.baseline_id == baseline.baseline_id
        assert any(r.kind == "scenario" and r.scenario_id == "extraction" for r in comparison.regressions)
        assert any(r.kind == "grader" and r.grader_id == "schema" for r in comparison.regressions)
        assert comparison.promotion_blocked == critical
    if critical:
        with pytest.raises(RegressionGateFailedError):
            factory.approve_version(ctx, next_version.id)
        with pytest.raises(RegressionGateFailedError):
            factory.publish_version(ctx, next_version.id)
        with pytest.raises(RegressionGateFailedError):
            factory.approval_engine.grant_approval(ctx, "agent_version", next_version.id, next_version.payload_hash)
        with db.session(write=True) as s:
            with pytest.raises(RegressionGateFailedError):
                BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id,
                    expected_baseline_id=baseline.baseline_id, reason="Cannot waive critical regression.")
            s.rollback()
        with db.session() as s:
            from database.schema import AuditEventModel
            assert s.query(AuditEventModel).filter_by(event_type="bench.promotion.blocked").count() >= 3
    else:
        factory.approve_version(ctx, next_version.id)
        assert factory.publish_version(ctx, next_version.id).status == "published"


@pytest.mark.asyncio
async def test_metric_policy_blocks_even_when_all_graders_pass(lifecycle, monkeypatch):
    suite = generic_suite(regression_policy=RegressionPolicy(max_latency_increase_seconds=0.05, max_token_increase=1))
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch, suite)
    next_version = candidate(factory, ctx, bp)
    runtime.latency, runtime.tokens = 0.1, 60
    evaluation = await factory.evaluate_version_with_bench(ctx, next_version.id)
    assert evaluation.passed and all(g.passed for s in evaluation.scenario_results for g in s.grader_results)
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
        assert comparison.metrics["latency_seconds"].delta > 0.05
        assert comparison.metrics["total_tokens"].delta == 20
        assert comparison.metrics["cost_usd"].state == "unavailable"
        assert len(comparison.critical_regressions) == 2
    with pytest.raises(RegressionGateFailedError):
        factory.approve_version(ctx, next_version.id)
    with pytest.raises(RegressionGateFailedError):
        factory.publish_version(ctx, next_version.id)


@pytest.mark.asyncio
async def test_baseline_change_invalidates_comparison_and_requires_new_human_review(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch)
    first, second = candidate(factory, ctx, bp), candidate(factory, ctx, bp, "4.0.0")
    await factory.evaluate_version_with_bench(ctx, first.id)
    await factory.evaluate_version_with_bench(ctx, second.id)
    _first_approval = factory.approve_version(ctx, first.id)
    old_approval = factory.approve_version(ctx, second.id)
    factory.publish_version(ctx, first.id)
    with db.session() as s:
        with pytest.raises(QualityGateFailedError, match="stale"):
            BenchRegressionRepository(s, db.evidence_signer).verify_current_comparison(ctx, old_approval.regression_comparison_id)
    with pytest.raises(ApprovalRequiredError):
        factory.publish_version(ctx, second.id)
    refreshed = factory.approve_version(ctx, second.id)
    assert refreshed.approval_id != old_approval.approval_id
    assert refreshed.regression_comparison_id != old_approval.regression_comparison_id
    assert factory.publish_version(ctx, second.id).status == "published"


@pytest.mark.asyncio
async def test_suite_evolution_requires_explicit_governed_rebaseline(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch)
    old = generic_suite().model_dump(mode="json")
    old["suite_hash"], old["evaluation_version"] = "", "2.2.0"
    old["scenarios"][0]["scenario_version"] = "1.1.0"
    install_generic_suite(monkeypatch, type(generic_suite()).model_validate(old))
    next_version = candidate(factory, ctx, bp)
    result = await factory.evaluate_version_with_bench(ctx, next_version.id)
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
        assert comparison.state == "incompatible" and comparison.promotion_blocked
    with pytest.raises(RegressionGateFailedError):
        factory.approve_version(ctx, next_version.id)
    with db.session(write=True) as s:
        with pytest.raises(RegressionGateFailedError):
            BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id,
                expected_baseline_id=baseline.baseline_id, reason="Missing explicit transition intent.")
        s.rollback()
    with db.session(write=True) as s:
        replacement = BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id,
            expected_baseline_id=baseline.baseline_id, reason="Admin reviewed evaluator 2.2.0 configuration transition.", transition=True)
        assert replacement.generation == 2 and replacement.acceptance == "suite_transition"
    factory.approve_version(ctx, next_version.id)
    assert factory.publish_version(ctx, next_version.id).status == "published"


@pytest.mark.asyncio
async def test_published_history_cannot_use_no_baseline_bootstrap(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    prior = await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    # Existing deployment upgraded from schema 010 has published history and no baseline.
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET status='published', published_at=CURRENT_TIMESTAMP WHERE id=:id"), {"id": version.id})
    next_version = candidate(factory, ctx, bp)
    await factory.evaluate_version_with_bench(ctx, next_version.id)
    with db.session() as s:
        comparison = BenchRegressionRepository(s, db.evidence_signer).compare(ctx, next_version.id)
        assert comparison.state == "baseline_required" and comparison.promotion_blocked
    with pytest.raises(RegressionGateFailedError):
        factory.approve_version(ctx, next_version.id)
    # An admin can adopt the verified historical publication, never an arbitrary new candidate.
    with db.session(write=True) as s:
        baseline = BenchRegressionRepository(s, db.evidence_signer).accept(ctx, prior.evaluation_id,
            reason="Adopt verified prior publication following database upgrade.")
        assert baseline.evaluation.version_id == version.id
    factory.approve_version(ctx, next_version.id)
    assert factory.publish_version(ctx, next_version.id).status == "published"


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
async def test_concurrent_acceptance_uses_compare_and_swap_without_losing_history(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch)
    versions = [candidate(factory, ctx, bp, f"{n}.0.0") for n in (3, 4)]
    results = [await factory.evaluate_version_with_bench(ctx, v.id) for v in versions]
    barrier = threading.Barrier(2)
    def accept(result):
        barrier.wait(timeout=5)
        try:
            with db.session(write=True) as s:
                return BenchRegressionRepository(s, db.evidence_signer).accept(ctx, result.evaluation_id,
                    expected_baseline_id=baseline.baseline_id, reason="Concurrent authorized human baseline review.")
        except QualityGateFailedError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(accept, results))
    assert sum(isinstance(x, QualityGateFailedError) for x in outcomes) == 1
    with db.session() as s:
        repo = BenchRegressionRepository(s, db.evidence_signer)
        assert repo.current(ctx, bp.id).generation == 2
        assert s.query(BenchBaselineModel).count() == 2


@pytest.mark.asyncio
async def test_later_failed_evaluation_invalidates_prior_comparison(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch)
    next_version = candidate(factory, ctx, bp)
    await factory.evaluate_version_with_bench(ctx, next_version.id)
    approval = factory.approve_version(ctx, next_version.id)
    runtime.output = "malformed"
    result = await factory.evaluate_version_with_bench(ctx, next_version.id)
    assert not result.passed
    with db.session() as s:
        with pytest.raises(QualityGateFailedError):
            BenchRegressionRepository(s, db.evidence_signer).verify_current_comparison(ctx, approval.regression_comparison_id)
    with pytest.raises(QualityGateFailedError):
        factory.publish_version(ctx, next_version.id)


@pytest.mark.asyncio
async def test_publication_failure_rolls_back_baseline_pointer_history_and_audit(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch)
    next_version = candidate(factory, ctx, bp)
    await factory.evaluate_version_with_bench(ctx, next_version.id)
    factory.approve_version(ctx, next_version.id)
    original = factory.audit_logger.record
    def fail_publication(event_type, *args, **kwargs):
        if event_type == "factory.version.published":
            raise RuntimeError("Isolated audit persistence failure")
        return original(event_type, *args, **kwargs)
    monkeypatch.setattr(factory.audit_logger, "record", fail_publication)
    with pytest.raises(RuntimeError, match="audit persistence"):
        factory.publish_version(ctx, next_version.id)
    with db.session() as s:
        from database.schema import AgentVersionModel, AuditEventModel
        assert BenchRegressionRepository(s, db.evidence_signer).current(ctx, bp.id).baseline_id == baseline.baseline_id
        assert s.get(AgentVersionModel, next_version.id).status == "approved"
        assert s.get(AgentVersionModel, next_version.id).published_at is None
        assert s.query(BenchBaselineModel).count() == 1
        assert s.query(AuditEventModel).filter_by(event_type="bench.baseline.superseded").count() == 0


@pytest.mark.asyncio
async def test_concurrent_publication_rechecks_baseline_and_expires_other_review(lifecycle, monkeypatch):
    db, ctx, runtime, factory, bp, version, _, baseline = await accepted(lifecycle, monkeypatch)
    versions = [candidate(factory, ctx, bp, f"{number}.0.0") for number in (3, 4)]
    for version in versions:
        await factory.evaluate_version_with_bench(ctx, version.id)
        factory.approve_version(ctx, version.id)
    barrier = threading.Barrier(2)
    def publish(version):
        barrier.wait(timeout=5)
        try:
            return factory.publish_version(ctx, version.id)
        except ApprovalRequiredError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(publish, versions))
    assert sum(isinstance(outcome, ApprovalRequiredError) for outcome in outcomes) == 1
    with db.session() as s:
        from database.schema import AgentVersionModel
        assert s.query(AgentVersionModel).filter_by(blueprint_id=bp.id, status="published").count() == 1
        assert BenchRegressionRepository(s, db.evidence_signer).current(ctx, bp.id).generation == 2
