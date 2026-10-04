"""Quality Gate enforcement for Agent publication.

Prevents agents from being approved or published if benchmark safety/accuracy tests fail.
Complies with ARYN-ARCH-001 Section 06 and AGENTS.md rule 6.
"""

from __future__ import annotations

from packages.contracts.bench import BenchEvaluationResult


class QualityGateFailedError(Exception):
    """Raised when an agent version fails the required Bench evaluation quality gate."""
    pass


class BenchQualityGate:
    """Enforces that an agent version satisfies benchmark criteria before promotion/publishing."""

    def __init__(self, min_score_threshold: float = 1.0) -> None:
        self.min_score_threshold = min_score_threshold

    def enforce(self, evaluation: BenchEvaluationResult) -> None:
        """Evaluates whether the benchmark result passes the quality threshold."""
        if not evaluation.passed or evaluation.score < self.min_score_threshold:
            failures = [r.name for r in evaluation.scenario_results if not r.passed]
            raise QualityGateFailedError(
                f"Quality gate rejected agent version '{evaluation.version_id}'. "
                f"Score {evaluation.score} does not meet required threshold {self.min_score_threshold}. "
                f"Failed scenarios ({len(failures)}): {failures}."
            )
