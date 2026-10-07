"""Deterministic aggregation shared by execution and stored evidence revalidation."""
from packages.contracts.bench import EvaluationState, QualityGateDecision, ScenarioResult


STATE_PRIORITY = (EvaluationState.RUNTIME_ERROR, EvaluationState.INVALID_EVIDENCE,
                  EvaluationState.UNVERIFIABLE, EvaluationState.POLICY_VIOLATION, EvaluationState.FAILED)


def aggregate_state(states):
    return next((state for state in STATE_PRIORITY if state in states), EvaluationState.PASSED)


def aggregate_scenario(scenario, execution, graders):
    state = aggregate_state([g.state for g in graders])
    if execution.runtime_status != "completed" or execution.runtime_error:
        state = EvaluationState.RUNTIME_ERROR
    passed = state == EvaluationState.PASSED
    failure = next((g.reason for g in graders if not g.passed), None)
    if state == EvaluationState.RUNTIME_ERROR:
        failure = execution.runtime_error or "runtime_not_completed"
    usage = execution.usage or {}
    usage = {key: value if type(value) is int and value >= 0 else 0 for key, value in usage.items()}
    return ScenarioResult(
        scenario_id=scenario.scenario_id, scenario_version=scenario.scenario_version,
        name=scenario.name, category=scenario.category, passed=passed, score=1.0 if passed else 0.0,
        state=state, actual_output=execution.output, latency_seconds=execution.latency_seconds,
        failure_reason=failure, actual_model=execution.reported_model, runtime_status=execution.runtime_status,
        input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
        total_tokens=usage.get("total_tokens", 0), execution=execution, grader_results=graders,
    )


def aggregate_suite(suite, results, reference=None):
    count = sum(result.passed for result in results)
    score = round(count / len(suite.scenarios), 4)
    threshold = max(suite.min_score_threshold, reference.min_score_threshold if reference else 0)
    required = list(dict.fromkeys([*suite.required_scenarios, *(reference.required_scenarios if reference else [])]))
    by_id = {r.scenario_id: r for r in results}
    unsafe = any(r.state in {EvaluationState.INVALID_EVIDENCE, EvaluationState.UNVERIFIABLE,
                            EvaluationState.RUNTIME_ERROR, EvaluationState.POLICY_VIOLATION} for r in results)
    passed = score >= threshold and not unsafe and all(by_id.get(key) and by_id[key].passed for key in required)
    state = EvaluationState.PASSED if passed else aggregate_state([r.state for r in results])
    if not passed and state == EvaluationState.PASSED:
        state = EvaluationState.FAILED
    decision = QualityGateDecision(passed=passed, reason="suite_policy_satisfied" if passed else "suite_policy_rejected",
                                   min_score_threshold=threshold, required_scenarios=required)
    return count, score, state, decision
