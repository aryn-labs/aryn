"""Evidence normalization and reproducible validation; no suite content rules here."""
from __future__ import annotations

import math
from pydantic import TypeAdapter
from packages.contracts.bench import (
    ActionEvidence, IdempotencyObservation, ScenarioExecutionEvidence, SuiteAggregateResult, EvaluationReference, evidence_hash,
)
from modules.bench.graders import GradingContext, execute_graders
from modules.bench.aggregation import aggregate_scenario, aggregate_suite


def grading_context(evaluation, scenario, execution, *, signer=None, approval_authority=None):
    return GradingContext(
        scenario=scenario, execution=execution, evaluation_id=evaluation.evaluation_id,
        suite_id=evaluation.suite_id, suite_hash=evaluation.suite_hash, version_id=evaluation.version_id,
        payload_hash=evaluation.payload_hash, requested_model=evaluation.requested_model,
        runtime_adapter=evaluation.runtime_adapter, organization_id=execution.organization_id,
        project_id=execution.project_id, output_contract=evaluation.output_contract,
        agent_tool_grants=tuple(evaluation.agent_tool_grants), agent_forbidden_actions=tuple(evaluation.agent_forbidden_actions),
        signer=signer, approval_authority=approval_authority,
    )


def normalize_observations(evidence, result):
    """Accept supported adapter fields only; malformed supplied evidence fails closed."""
    if result.execution_evidence is None:
        return
    try:
        data = result.execution_evidence
        allowed = {"run_id", "trace_complete", "actions", "idempotency_observations", "cost_usd", "resources"}
        if not isinstance(data, dict) or set(data) - allowed or data.get("run_id") != result.run_id:
            raise ValueError("Observation identity differs.")
        if "trace_complete" in data:
            if type(data["trace_complete"]) is not bool:
                raise ValueError("Invalid trace completeness.")
            evidence.trace_available = data["trace_complete"]
            if "actions" not in data:
                raise ValueError("Action observations missing.")
        evidence.actions = TypeAdapter(list[ActionEvidence]).validate_python(data.get("actions", []), strict=True)
        evidence.idempotency_observations = TypeAdapter(list[IdempotencyObservation]).validate_python(
            data.get("idempotency_observations", []), strict=True)
        cost = data.get("cost_usd")
        resources = data.get("resources", {})
        if cost is not None and (type(cost) not in {int, float} or not math.isfinite(cost) or cost < 0):
            raise ValueError("Invalid cost observation.")
        if not isinstance(resources, dict) or any(type(v) not in {int, float} or not math.isfinite(v) or v < 0 for v in resources.values()):
            raise ValueError("Invalid resource observation.")
        evidence.cost_usd = cost
        evidence.resources = data.get("resources", {})
    except (ValueError, TypeError):
        evidence.evidence_errors.append("adapter_observations_malformed")


def validate_legacy(evaluation, suite):
    """Revalidate the original evidence layout only for an explicitly configured legacy hash.

    Its original HMAC is verified by the repository. It never gains new grader claims.
    """
    import re
    if not suite.legacy_suite_hash or evaluation.suite_hash != suite.legacy_suite_hash:
        raise ValueError("Legacy suite hash unavailable or differs.")
    for scenario, result in zip(suite.scenarios, evaluation.scenario_results):
        passed = (result.runtime_status == "completed" and result.actual_model == evaluation.requested_model
                  and all(type(v) is int and v >= 0 for v in (result.input_tokens, result.output_tokens, result.total_tokens))
                  and result.total_tokens == result.input_tokens + result.output_tokens
                  and math.isfinite(result.latency_seconds) and 0 <= result.latency_seconds <= scenario.max_latency_seconds)
        # Content rules belong to the suite's grader specifications, including historical evidence.
        for spec in scenario.graders:
            if spec.type == "text_pattern":
                passed = passed and (not spec.expected_pattern or bool(re.search(spec.expected_pattern, result.actual_output)))
                passed = passed and (not spec.forbidden_pattern or not re.search(spec.forbidden_pattern, result.actual_output))
        if (result.name != scenario.name or result.category != scenario.category or result.passed != bool(passed)
                or result.score != float(bool(passed)) or bool(result.failure_reason) == bool(passed)
                or result.execution is not None or result.grader_results):
            raise ValueError("Legacy scenario evidence inconsistent.")
    count = sum(r.passed for r in evaluation.scenario_results)
    if (evaluation.passed_scenarios != count or evaluation.score != round(count / len(suite.scenarios), 4)
            or evaluation.passed != (count == len(suite.scenarios))):
        raise ValueError("Legacy aggregate differs.")


def validate_evaluation(evaluation, suite, *, reference=None, signer=None, approval_authority=None):
    if (not evaluation.evaluation_id or not evaluation.payload_hash or not evaluation.requested_model
            or not evaluation.runtime_adapter or evaluation.evaluation_version != suite.evaluation_version
            or evaluation.suite_id not in [suite.suite_id, *suite.aliases]
            or evaluation.total_scenarios != len(suite.scenarios)
            or [r.scenario_id for r in evaluation.scenario_results] != suite.scenario_ids):
        raise ValueError("Incomplete or obsolete evaluation evidence.")
    if evaluation.evidence_format == 1:
        validate_legacy(evaluation, suite)
        return
    if evaluation.suite_id != suite.suite_id or evaluation.suite_hash != suite.suite_hash:
        raise ValueError("Suite configuration differs.")
    for scenario, result in zip(suite.scenarios, evaluation.scenario_results):
        if result.execution is None:
            raise ValueError("Execution evidence missing.")
        # Reparse copies because model_copy and runtime mutation can bypass Pydantic validation.
        execution = ScenarioExecutionEvidence.model_validate(result.execution.model_dump(mode="json"))
        ctx = grading_context(evaluation, scenario, execution, signer=signer, approval_authority=approval_authority)
        graders = execute_graders(ctx, suite.resource_limits)
        expected = aggregate_scenario(scenario, execution, graders)
        if expected.model_dump(mode="json") != result.model_dump(mode="json"):
            raise ValueError("Scenario or grader evidence differs from deterministic recomputation.")
    if evaluation.evaluation_reference is None:
        raise ValueError("Promotion reference missing.")
    captured_reference = EvaluationReference.model_validate(evaluation.evaluation_reference.model_dump())
    if reference is not None and captured_reference != reference:
        raise ValueError("Captured promotion reference differs from current agent configuration.")
    from modules.bench.scenarios import get_bench_suite
    if get_bench_suite(captured_reference.suite_id).suite_id != suite.suite_id:
        raise ValueError("Promotion suite differs.")
    suite_count, suite_score, suite_state, suite_decision = aggregate_suite(suite, evaluation.scenario_results)
    expected_suite = SuiteAggregateResult(passed=suite_decision.passed, total_scenarios=len(suite.scenarios),
        passed_scenarios=suite_count, score=suite_score, state=suite_state)
    if evaluation.suite_aggregate != expected_suite:
        raise ValueError("Suite aggregate differs.")
    count, score, state, decision = aggregate_suite(suite, evaluation.scenario_results, captured_reference)
    if (evaluation.passed_scenarios != count or evaluation.score != score
            or evaluation.state != state or evaluation.passed != decision.passed
            or evaluation.quality_gate != decision):
        raise ValueError("Aggregate or policy decision differs from deterministic recomputation.")
