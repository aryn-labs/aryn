"""Quality Gate enforcement for Agent publication.

Prevents agents from being approved or published if benchmark safety/accuracy tests fail.
Complies with ARYN-ARCH-001 Section 06 and AGENTS.md rule 6.
"""

from __future__ import annotations

from typing import Optional
from packages.contracts.bench import BenchEvaluationResult
from packages.contracts.bench import RESEARCH_BENCH_VERSION
from packages.contracts.agent import AgentEvaluationReference
from modules.bench.scenarios import (
    get_bench_suite,
    get_standard_research_bench_scenarios,
    research_suite_hash,
)
import math
import re


class QualityGateFailedError(Exception):
    """Raised when an agent version fails the required Bench evaluation quality gate."""
    pass


class BenchQualityGate:
    """Enforces that an agent version satisfies benchmark criteria before promotion/publishing."""

    def __init__(self, min_score_threshold: float = 1.0) -> None:
        self.min_score_threshold = min_score_threshold

    def enforce(
        self,
        evaluation: BenchEvaluationResult,
        evaluation_reference: Optional[AgentEvaluationReference] = None,
    ) -> None:
        """Evaluates whether the benchmark result passes the quality threshold."""
        self.validate_evidence(evaluation, evaluation_reference=evaluation_reference)
        min_threshold = (
            evaluation_reference.min_score_threshold
            if evaluation_reference is not None
            else self.min_score_threshold
        )
        if not evaluation.passed or evaluation.score < min_threshold:
            failures = [r.name for r in evaluation.scenario_results if not r.passed]
            raise QualityGateFailedError(
                f"Quality gate rejected agent version '{evaluation.version_id}'. "
                f"Score {evaluation.score} does not meet required threshold {min_threshold}. "
                f"Failed scenarios ({len(failures)}): {failures}."
            )
        if evaluation_reference is not None:
            results_by_id = {r.scenario_id: r for r in evaluation.scenario_results}
            for req_scen in evaluation_reference.required_scenarios:
                if req_scen not in results_by_id:
                    raise QualityGateFailedError(
                        f"Quality gate rejected: required scenario '{req_scen}' was not evaluated."
                    )
                if not results_by_id[req_scen].passed:
                    raise QualityGateFailedError(
                        f"Quality gate rejected: required scenario '{req_scen}' failed in evaluation."
                    )

    @staticmethod
    def validate_evidence(
        evaluation: BenchEvaluationResult,
        evaluation_reference: Optional[AgentEvaluationReference] = None,
    ) -> None:
        """Recompute every scenario and aggregate; booleans and scores are not authority."""
        suite_id = getattr(evaluation, "suite_id", "research-safety-1.2.0") or "research-safety-1.2.0"
        suite_def = get_bench_suite(suite_id)
        if suite_def is None:
            raise QualityGateFailedError(f"Quality gate rejected unknown Bench suite '{suite_id}'.")
        suite = suite_def.scenarios
        valid = (
            evaluation.evaluation_version in (suite_def.evaluation_version, RESEARCH_BENCH_VERSION)
            and evaluation.suite_hash == suite_def.suite_hash
            and bool(evaluation.runtime_adapter)
            and bool(evaluation.payload_hash)
            and bool(evaluation.requested_model)
            and evaluation.total_scenarios == len(suite)
            and [r.scenario_id for r in evaluation.scenario_results] == suite_def.scenario_ids
        )
        if not valid:
            raise QualityGateFailedError("Quality gate rejected incomplete or obsolete Bench evidence.")
        for spec, result in zip(suite, evaluation.scenario_results):
            usage_valid = (
                min(result.input_tokens, result.output_tokens, result.total_tokens) >= 0
                and result.total_tokens == result.input_tokens + result.output_tokens
            )
            passed = (
                result.runtime_status == "completed"
                and result.actual_model == evaluation.requested_model
                and usage_valid
                and math.isfinite(result.latency_seconds)
                and 0 <= result.latency_seconds <= spec.max_latency_seconds
                and (not spec.expected_pattern or bool(re.search(spec.expected_pattern, result.actual_output)))
                and (not spec.forbidden_pattern or not re.search(spec.forbidden_pattern, result.actual_output))
            )
            if (result.name != spec.name or result.category != spec.category
                    or result.passed != passed or result.score != (1.0 if passed else 0.0)
                    or bool(result.failure_reason) == passed):
                raise QualityGateFailedError("Quality gate rejected inconsistent scenario evidence.")
        count = sum(r.passed for r in evaluation.scenario_results)
        if (evaluation.passed_scenarios != count or evaluation.score != round(count / len(suite), 4)
                or evaluation.passed != (count == len(suite))):
            raise QualityGateFailedError("Quality gate rejected inconsistent aggregate evidence.")

        if evaluation_reference is not None:
            expected_suites = {evaluation_reference.suite_id, "research-safety-1.2.0", "research-safety"}
            if suite_id not in expected_suites and evaluation.suite_id not in expected_suites:
                raise QualityGateFailedError(
                    f"Quality gate rejected: evaluation suite '{suite_id}' does not match "
                    f"required suite '{evaluation_reference.suite_id}'."
                )
