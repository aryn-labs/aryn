"""Quality Gate enforcement for Agent publication.

Prevents agents from being approved or published if benchmark safety/accuracy tests fail.
Complies with ARYN-ARCH-001 Section 06 and AGENTS.md rule 6.
"""

from __future__ import annotations

from packages.contracts.bench import BenchEvaluationResult
from packages.contracts.bench import RESEARCH_BENCH_VERSION
from modules.bench.scenarios import get_standard_research_bench_scenarios, research_suite_hash
import math
import re


class QualityGateFailedError(Exception):
    """Raised when an agent version fails the required Bench evaluation quality gate."""
    pass


class BenchQualityGate:
    """Enforces that an agent version satisfies benchmark criteria before promotion/publishing."""

    def __init__(self, min_score_threshold: float = 1.0) -> None:
        self.min_score_threshold = min_score_threshold

    def enforce(self, evaluation: BenchEvaluationResult) -> None:
        """Evaluates whether the benchmark result passes the quality threshold."""
        self.validate_evidence(evaluation)
        if not evaluation.passed or evaluation.score < self.min_score_threshold:
            failures = [r.name for r in evaluation.scenario_results if not r.passed]
            raise QualityGateFailedError(
                f"Quality gate rejected agent version '{evaluation.version_id}'. "
                f"Score {evaluation.score} does not meet required threshold {self.min_score_threshold}. "
                f"Failed scenarios ({len(failures)}): {failures}."
            )

    @staticmethod
    def validate_evidence(evaluation: BenchEvaluationResult) -> None:
        """Recompute every scenario and aggregate; booleans and scores are not authority."""
        suite = get_standard_research_bench_scenarios()
        valid = (
            evaluation.evaluation_version == RESEARCH_BENCH_VERSION
            and evaluation.suite_hash == research_suite_hash()
            and bool(evaluation.runtime_adapter)
            and bool(evaluation.payload_hash)
            and bool(evaluation.requested_model)
            and evaluation.total_scenarios == len(suite)
            and [r.scenario_id for r in evaluation.scenario_results] == [s.scenario_id for s in suite]
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
