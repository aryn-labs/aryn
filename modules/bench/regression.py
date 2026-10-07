"""Deterministic comparison of independently verified Bench evidence.

The repository validates tenant, version, signatures and grader recomputation first.
This module never grants baseline authority and contains no suite-specific rules.
"""
from __future__ import annotations

import math
import inspect
from functools import wraps
from packages.contracts.bench import (
    EvaluationState, RegressionComparison, RegressionFinding, RegressionPolicy,
    ScenarioComparison, GraderComparison, MetricDelta,
)

UNSAFE_STATES = frozenset({EvaluationState.POLICY_VIOLATION, EvaluationState.INVALID_EVIDENCE,
    EvaluationState.UNVERIFIABLE, EvaluationState.RUNTIME_ERROR})
GOVERNANCE_GRADERS = frozenset({"evidence_integrity", "model_identity", "forbidden_action",
    "approval_enforcement", "idempotency"})


def audit_regression_denial(operation):
    """Persist denied governance attempts after the enclosing transaction rolls back."""
    signature = inspect.signature(operation)
    @wraps(operation)
    def guarded(authority, context, *args, **kwargs):
        from database.repositories.bench_regression_repo import BenchRegressionRepository, RegressionGateFailedError
        try:
            return operation(authority, context, *args, **kwargs)
        except RegressionGateFailedError as exc:
            # The owning Factory transaction handles calls using its active session.
            if signature.bind_partial(authority, context, *args, **kwargs).arguments.get("session") is None:
                from modules.core.audit.logger import AuditLogger
                from packages.contracts.core import AuditStatus
                with authority.db_manager.session(write=True) as session:
                    comparison = BenchRegressionRepository(session, authority.db_manager.evidence_signer).compare(
                        context, exc.comparison.candidate.version_id, persist=True)
                    AuditLogger(authority.db_manager).record("bench.promotion.blocked", context,
                        comparison.candidate.version_id, AuditStatus.DENIED,
                        {"comparison_id": comparison.comparison_id, "baseline_id": comparison.baseline_id,
                         "denied_comparison_id": exc.comparison.comparison_id,
                         "operation": operation.__name__, "reason": exc.comparison.reason}, session=session)
            raise
    return guarded


def metric_delta(before, after):
    invalid = any(value is not None and (type(value) not in {int, float}
        or not math.isfinite(value) or value < 0) for value in (before, after))
    if invalid:
        return MetricDelta(state="invalid")
    return MetricDelta(state="unavailable" if before is None or after is None else "comparable",
        baseline=before, candidate=after, delta=after - before if before is not None and after is not None else None)


def measurements(evaluation):
    scenarios = evaluation.scenario_results
    values = {"latency_seconds": sum(s.latency_seconds for s in scenarios),
              "total_tokens": sum(s.total_tokens for s in scenarios)}
    executions = [s.execution for s in scenarios]
    values["cost_usd"] = (sum(e.cost_usd for e in executions)
        if executions and all(e is not None and e.cost_usd is not None for e in executions) else None)
    if evaluation.evidence_format == 2:
        usage = [e.usage if e else None for e in executions]
        values["total_tokens"] = (sum(u["total_tokens"] for u in usage)
            if usage and all(isinstance(u, dict) and type(u.get("total_tokens")) is int
                and u["total_tokens"] >= 0 for u in usage) else None)
    names = {name for e in executions if e for name in e.resources}
    for name in names:
        values[f"resource:{name}"] = (sum(e.resources[name] for e in executions)
            if all(e and name in e.resources for e in executions) else None)
    return values


def block(comparison, state, reason, **details):
    comparison.state = state
    comparison.reason = reason
    comparison.promotion_blocked = True
    finding = RegressionFinding(kind="comparability" if state == "incompatible" else "evidence",
        reason=reason, critical=True, details=details)
    comparison.regressions.append(finding)
    comparison.critical_regressions.append(finding)
    return comparison


def compare_evaluations(comparison: RegressionComparison, baseline, candidate, suite):
    """Compare by stable scenario/grader identities, never array position or aggregate PASS."""
    if baseline.blueprint_id != candidate.blueprint_id or candidate.blueprint_id != comparison.blueprint_id:
        return block(comparison, "incompatible", "blueprint_identity_mismatch")
    for evaluation, identity in ((baseline, comparison.baseline), (candidate, comparison.candidate)):
        if identity is None or (evaluation.evaluation_id, evaluation.version_id, evaluation.payload_hash) != (
                identity.evaluation_id, identity.version_id, identity.payload_hash):
            return block(comparison, "invalid", "evaluation_identity_mismatch")
        if evaluation.evidence_format == 2 and any(s.execution is None or (
                s.execution.organization_id, s.execution.project_id) != (comparison.organization_id, comparison.project_id)
                for s in evaluation.scenario_results):
            return block(comparison, "invalid", "execution_scope_mismatch")
    comparison.baseline_score = baseline.score
    comparison.candidate_score = candidate.score
    comparison.score_delta = round(candidate.score - baseline.score, 8)
    if ((baseline.suite_id, baseline.evaluation_version, baseline.suite_hash, baseline.evidence_format)
            != (candidate.suite_id, candidate.evaluation_version, candidate.suite_hash, candidate.evidence_format)):
        return block(comparison, "incompatible", "suite_or_evidence_format_changed")
    before = {s.scenario_id: s for s in baseline.scenario_results}
    after = {s.scenario_id: s for s in candidate.scenario_results}
    if (len(before) != len(baseline.scenario_results) or len(after) != len(candidate.scenario_results)
            or set(before) != set(after) or set(before) != set(suite.scenario_ids)):
        return block(comparison, "incompatible", "scenario_identities_changed",
            missing=sorted(set(before) - set(after)), added=sorted(set(after) - set(before)))
    policy = suite.regression_policy or RegressionPolicy()
    required = set(suite.required_scenarios) | set(policy.critical_scenarios)
    for evaluation in (baseline, candidate):
        if evaluation.evaluation_reference:
            required.update(evaluation.evaluation_reference.required_scenarios)
    for scenario_id in sorted(before):
        old, new = before[scenario_id], after[scenario_id]
        if old.scenario_version != new.scenario_version:
            return block(comparison, "incompatible", "scenario_version_changed", scenario_id=scenario_id)
        old_state = old.state if baseline.evidence_format == 2 else (EvaluationState.PASSED if old.passed else EvaluationState.FAILED)
        new_state = new.state if candidate.evidence_format == 2 else (EvaluationState.PASSED if new.passed else EvaluationState.FAILED)
        regressed = old_state == EvaluationState.PASSED and new_state != EvaluationState.PASSED
        critical = regressed and (new_state in UNSAFE_STATES or scenario_id in required)
        row = ScenarioComparison(scenario_id=scenario_id, scenario_version=old.scenario_version,
            baseline_state=old_state, candidate_state=new_state, candidate_reason=new.failure_reason,
            regression=regressed, critical=critical)
        comparison.scenarios.append(row)
        if regressed:
            comparison.regressions.append(RegressionFinding(kind="scenario", reason="scenario_state_regressed",
                critical=critical, scenario_id=scenario_id, baseline_state=old_state, candidate_state=new_state,
                details={"candidate_reason": new.failure_reason}))
        if baseline.evidence_format == 1:
            continue
        old_graders = {(g.grader_id, g.grader_type, g.grader_version): g for g in old.grader_results}
        new_graders = {(g.grader_id, g.grader_type, g.grader_version): g for g in new.grader_results}
        if (len(old_graders) != len(old.grader_results) or len(new_graders) != len(new.grader_results)
                or set(old_graders) != set(new_graders)):
            return block(comparison, "incompatible", "grader_identities_changed", scenario_id=scenario_id)
        for key in sorted(old_graders):
            previous, current = old_graders[key], new_graders[key]
            regression = previous.state == EvaluationState.PASSED and current.state != EvaluationState.PASSED
            hard = regression and (current.state in UNSAFE_STATES or scenario_id in required
                or current.grader_type in GOVERNANCE_GRADERS or current.grader_id in policy.critical_graders)
            row.graders.append(GraderComparison(grader_id=key[0], grader_type=key[1], grader_version=key[2],
                baseline_state=previous.state, candidate_state=current.state, candidate_reason=current.reason,
                regression=regression, critical=hard))
            if regression:
                comparison.regressions.append(RegressionFinding(kind="grader", reason="grader_state_regressed",
                    critical=hard, scenario_id=scenario_id, grader_id=key[0], baseline_state=previous.state,
                    candidate_state=current.state, details={"grader_type": key[1], "candidate_reason": current.reason}))
    before_metrics, after_metrics = measurements(baseline), measurements(candidate)
    for name in sorted(set(before_metrics) | set(after_metrics) | {f"resource:{n}" for n in policy.max_resource_increases}):
        comparison.metrics[name] = metric_delta(before_metrics.get(name), after_metrics.get(name))
    limits = {"latency_seconds": policy.max_latency_increase_seconds, "total_tokens": policy.max_token_increase,
        "cost_usd": policy.max_cost_increase_usd, **{f"resource:{n}": v for n, v in policy.max_resource_increases.items()}}
    for name, delta in comparison.metrics.items():
        limit = limits.get(name)
        if limit is not None and delta.state != "comparable":
            comparison.regressions.append(RegressionFinding(kind="metric", reason="required_metric_unverifiable",
                critical=True, details={"metric": name, "state": delta.state}))
        elif delta.delta is not None and delta.delta > 0:
            comparison.regressions.append(RegressionFinding(kind="metric", reason="metric_increased",
                critical=limit is not None and delta.delta > limit, details={"metric": name, "delta": delta.delta, "limit": limit}))
    if comparison.score_delta < 0:
        comparison.regressions.append(RegressionFinding(kind="metric", reason="score_decreased",
            critical=policy.max_score_drop is not None and -comparison.score_delta > policy.max_score_drop,
            details={"delta": comparison.score_delta, "limit": policy.max_score_drop}))
    for field in ("requested_model", "runtime_adapter"):
        if getattr(baseline, field) != getattr(candidate, field):
            comparison.provenance_differences[field] = {"baseline": getattr(baseline, field), "candidate": getattr(candidate, field)}
    for scenario_id in sorted(before):
        old, new = before[scenario_id].execution, after[scenario_id].execution
        if old and new:
            changes = {name: {"baseline": getattr(old, name), "candidate": getattr(new, name)}
                for name in ("actual_model", "provider", "runtime_backend", "gateway") if getattr(old, name) != getattr(new, name)}
            if changes:
                comparison.provenance_differences[scenario_id] = changes
    comparison.state = "comparable"
    comparison.critical_regressions = [r for r in comparison.regressions if r.critical]
    comparison.promotion_blocked = bool(comparison.critical_regressions)
    comparison.reason = "critical_regression" if comparison.promotion_blocked else "comparison_completed"
    return comparison
