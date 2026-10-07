"""Suite-independent promotion policy over recomputed Bench evidence."""
from packages.contracts.agent import AgentEvaluationReference
from modules.bench.scenarios import get_bench_suite
from modules.bench.evidence import validate_evaluation


class QualityGateFailedError(Exception):
    pass


class BenchQualityGate:
    def __init__(self, min_score_threshold=1.0):
        self.min_score_threshold = min_score_threshold

    def enforce(self, evaluation, evaluation_reference=None, *, signer=None, approval_authority=None):
        self.validate_evidence(evaluation, evaluation_reference, signer=signer, approval_authority=approval_authority)
        suite = get_bench_suite(evaluation.suite_id)
        threshold = max(suite.min_score_threshold, evaluation_reference.min_score_threshold
                        if evaluation_reference else self.min_score_threshold)
        required = set(suite.required_scenarios) | set(evaluation_reference.required_scenarios if evaluation_reference else [])
        by_id = {r.scenario_id: r for r in evaluation.scenario_results}
        if not evaluation.passed or evaluation.score < threshold or any(not by_id[key].passed for key in required):
            failures = [r.name for r in evaluation.scenario_results if not r.passed]
            raise QualityGateFailedError(
                f"Quality gate rejected agent version '{evaluation.version_id}'. Score {evaluation.score} "
                f"does not meet required threshold {threshold}. Failed scenarios ({len(failures)}): {failures}.")

    @staticmethod
    def validate_evidence(evaluation, evaluation_reference=None, *, signer=None, approval_authority=None):
        suite = get_bench_suite(evaluation.suite_id)
        if suite is None:
            raise QualityGateFailedError(f"Quality gate rejected unknown Bench suite '{evaluation.suite_id}'.")
        try:
            if evaluation_reference is not None:
                reference = AgentEvaluationReference.model_validate(evaluation_reference.model_dump())
                expected = get_bench_suite(reference.suite_id)
                if expected.suite_id != suite.suite_id or reference.evaluation_version != evaluation.evaluation_version:
                    raise ValueError("Evaluation reference differs.")
                if reference.evaluation_id is not None and reference.evaluation_id != evaluation.evaluation_id:
                    raise ValueError("Evaluation identity differs.")
            validate_evaluation(evaluation, suite, reference=evaluation_reference,
                                signer=signer, approval_authority=approval_authority)
        except Exception as exc:
            raise QualityGateFailedError("Quality gate rejected malformed, inconsistent or obsolete Bench evidence.") from exc
