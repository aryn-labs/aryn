"""Comparison policy tests over isolated typed evidence, without governance claims."""
import pytest
import datetime
from packages.contracts.bench import (
    BenchEvaluationResult, EvaluationIdentity, EvaluationState, GraderResult, RegressionComparison,
    RegressionPolicy, ScenarioResult, evidence_hash,
)
from modules.bench.regression import compare_evaluations, metric_delta
from tests.bench_fixtures import generic_suite
from tests.unit.test_bench_graders import grading_context


def evaluations(suite=None):
    suite = suite or generic_suite(required_scenarios=[])
    scenarios = [ScenarioResult(scenario_id=s.scenario_id, name=s.name, category=s.category, passed=True,
        state="passed", score=1, actual_output='{"summary":"ok"}', latency_seconds=1, total_tokens=5,
        execution=grading_context(s).execution,
        grader_results=[GraderResult(grader_id=g.grader_id, grader_type=g.type, grader_version=g.version,
            state="passed", passed=True, reason="verified") for g in s.graders]) for s in suite.scenarios]
    baseline = BenchEvaluationResult(evaluation_id="prior", blueprint_id="blueprint", version_id="prior_version",
        passed=True, total_scenarios=2, passed_scenarios=2, score=1, scenario_results=scenarios,
        suite_id=suite.suite_id, evaluation_version=suite.evaluation_version, suite_hash=suite.suite_hash,
        payload_hash=evidence_hash({"version": 1}), evidence_format=2)
    return baseline, baseline.model_copy(deep=True, update={"evaluation_id": "candidate", "version_id": "candidate_version"}), suite


def comparison(baseline, candidate):
    def identity(e):
        return EvaluationIdentity(evaluation_id=e.evaluation_id, version_id=e.version_id, version_number="1.0.0",
            payload_hash=e.payload_hash, evidence_format=e.evidence_format, evidence_hash=evidence_hash(e.model_dump(mode="json")))
    return RegressionComparison(comparison_id="comparison", organization_id="org", project_id="project",
        blueprint_id="blueprint", baseline_id="baseline", baseline=identity(baseline), candidate=identity(candidate),
        suite_id=candidate.suite_id, evaluation_version=candidate.evaluation_version, suite_hash=candidate.suite_hash,
        compared_at="2026-10-08T00:00:00+00:00", state="comparable", reason="pending", promotion_blocked=False)


def test_pass_to_pass_is_comparable_by_identity_instead_of_position():
    before, after, suite = evaluations()
    after.scenario_results.reverse()
    result = compare_evaluations(comparison(before, after), before, after, suite)
    assert result.state == "comparable" and not result.regressions and not result.promotion_blocked
    assert result.score_delta == 0 and result.metrics["total_tokens"].delta == 0
    assert result.metrics["cost_usd"].state == "unavailable" and result.metrics["cost_usd"].delta is None


def test_default_policy_preserves_suite_configuration_hashes_written_before_regression_support():
    suite = generic_suite()
    previous_configuration = suite.model_dump(mode="json", exclude={"suite_hash", "regression_policy"})
    assert evidence_hash(previous_configuration) == suite.suite_hash


def test_persisted_timestamps_are_canonical_across_database_timezones():
    from database.repositories.bench_regression_repo import timestamp
    utc = datetime.datetime(2026, 10, 8, tzinfo=datetime.timezone.utc)
    local = utc.astimezone(datetime.timezone(datetime.timedelta(hours=7)))
    assert timestamp(utc) == timestamp(local) == timestamp(utc.replace(tzinfo=None))


@pytest.mark.parametrize("state,critical", [("failed", False), ("policy_violation", True),
    ("invalid_evidence", True), ("unverifiable", True), ("runtime_error", True)])
def test_scenario_state_regression_is_explicit(state, critical):
    before, after, suite = evaluations()
    after.scenario_results[0].state = EvaluationState(state)
    after.scenario_results[0].passed = False
    after.scenario_results[0].failure_reason = "deterministic_failure"
    result = compare_evaluations(comparison(before, after), before, after, suite)
    finding = next(r for r in result.regressions if r.kind == "scenario")
    assert finding.baseline_state == "passed" and finding.candidate_state == state
    assert finding.critical == critical and result.promotion_blocked == critical


@pytest.mark.parametrize("required,policy", [(["summary"], None), ([], RegressionPolicy(critical_scenarios=["summary"]))])
def test_required_and_policy_critical_scenario_failure_blocks(required, policy):
    before, after, suite = evaluations(generic_suite(required_scenarios=required, regression_policy=policy))
    after.scenario_results[0].state = EvaluationState.FAILED
    result = compare_evaluations(comparison(before, after), before, after, suite)
    assert result.promotion_blocked and result.critical_regressions[0].scenario_id == "summary"


@pytest.mark.parametrize("state", ["failed", "policy_violation", "invalid_evidence", "unverifiable"])
@pytest.mark.parametrize("grader_type", ["schema_validity", "model_identity", "evidence_integrity", "approval_enforcement", "idempotency"])
def test_grader_regressions_and_governance_criticality(state, grader_type):
    before, after, suite = evaluations()
    for evaluation in (before, after):
        evaluation.scenario_results[0].grader_results = [GraderResult(grader_id="stable", grader_type=grader_type,
            grader_version="1.0.0", state="passed", passed=True, reason="verified")]
    after.scenario_results[0].grader_results[0] = GraderResult(grader_id="stable", grader_type=grader_type,
        grader_version="1.0.0", state=state, passed=False, reason="observed_violation")
    result = compare_evaluations(comparison(before, after), before, after, suite)
    assert result.regressions[0].kind == "grader"
    assert result.promotion_blocked == (state != "failed" or grader_type != "schema_validity")


@pytest.mark.parametrize("change", ["scenario_missing", "scenario_added", "scenario_version", "grader_missing", "grader_version", "suite_hash", "suite_version", "evidence_format"])
def test_missing_or_changed_identities_never_pass(change):
    before, after, suite = evaluations()
    if change == "scenario_missing": after.scenario_results.pop()
    elif change == "scenario_added": after.scenario_results.append(after.scenario_results[0].model_copy(update={"scenario_id": "new"}))
    elif change == "scenario_version": after.scenario_results[0].scenario_version = "2.0.0"
    elif change == "grader_missing": after.scenario_results[0].grader_results.pop()
    elif change == "grader_version": after.scenario_results[0].grader_results[0].grader_version = "2.0.0"
    elif change == "suite_hash": after.suite_hash = "different"
    elif change == "suite_version": after.evaluation_version = "3.0.0"
    else: after.evidence_format = 1
    result = compare_evaluations(comparison(before, after), before, after, suite)
    assert result.state == "incompatible" and result.promotion_blocked


def test_score_latency_token_cost_resource_deltas_are_real_and_policy_bound():
    policy = RegressionPolicy(max_score_drop=0.2, max_latency_increase_seconds=1,
        max_token_increase=4, max_cost_increase_usd=0.1, max_resource_increases={"cpu": 1})
    before, after, suite = evaluations(generic_suite(required_scenarios=[], regression_policy=policy))
    after.score = 0.5
    for old, new in zip(before.scenario_results, after.scenario_results):
        old.execution.cost_usd, new.execution.cost_usd = 0.1, 0.2
        old.execution.resources, new.execution.resources = {"cpu": 1}, {"cpu": 2}
        new.execution.usage["total_tokens"] = 8
        new.latency_seconds = 2
    result = compare_evaluations(comparison(before, after), before, after, suite)
    assert result.score_delta == -0.5
    assert result.metrics["latency_seconds"].delta == 2
    assert result.metrics["total_tokens"].delta == 6
    assert result.metrics["cost_usd"].delta == pytest.approx(0.2)
    assert result.metrics["resource:cpu"].delta == 2
    assert result.promotion_blocked and len(result.critical_regressions) == 5


def test_required_missing_metric_is_unverifiable_and_critical():
    before, after, suite = evaluations(generic_suite(regression_policy=RegressionPolicy(max_cost_increase_usd=1)))
    result = compare_evaluations(comparison(before, after), before, after, suite)
    assert result.promotion_blocked and result.metrics["cost_usd"].delta is None
    assert result.critical_regressions[0].reason == "required_metric_unverifiable"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "1"])
def test_invalid_metric_does_not_create_fabricated_delta(value):
    result = metric_delta(value, 1)
    assert result.state == "invalid" and result.delta is None


@pytest.mark.parametrize("policy", [{"max_score_drop": -1}, {"max_resource_increases": {"cpu": -1}},
    {"max_latency_increase_seconds": float("nan")}, {"critical_scenarios": ["unknown"]}, {"critical_graders": ["unknown"]}])
def test_invalid_regression_policy_rejected(policy):
    with pytest.raises(ValueError): generic_suite(regression_policy=policy)


@pytest.mark.parametrize("change", ["blueprint", "payload", "evaluation", "tenant"])
def test_comparison_rejects_execution_or_version_identity_mismatch(change):
    before, after, suite = evaluations()
    result = comparison(before, after)
    if change == "blueprint": before.blueprint_id = "foreign"
    elif change == "payload": after.payload_hash = evidence_hash({"tampered": True})
    elif change == "evaluation": after.evaluation_id = "forged"
    else: after.scenario_results[0].execution.project_id = "foreign"
    result = compare_evaluations(result, before, after, suite)
    assert result.state in {"invalid", "incompatible"} and result.promotion_blocked
