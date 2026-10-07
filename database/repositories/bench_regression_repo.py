"""Tenant-scoped baseline history and revalidated deterministic comparisons."""
from __future__ import annotations

import datetime
import json
import uuid

from database.connection import DatabaseManager
from database.repositories.agent_repo import AgentRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.exceptions import TenantIsolationError
from database.schema import AgentVersionModel, BenchBaselineModel, BenchComparisonModel, MembershipModel
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from modules.bench.regression import block, compare_evaluations
from modules.bench.scenarios import get_bench_suite
from modules.core.audit.logger import AuditLogger
from modules.core.permissions.engine import PermissionEngine, PermissionDeniedError
from packages.contracts.agent import AgentVersion
from packages.contracts.bench import AcceptedBaseline, EvaluationIdentity, RegressionComparison, evidence_hash
from packages.contracts.core import ActorType, AuditStatus


class RegressionGateFailedError(QualityGateFailedError):
    def __init__(self, comparison):
        self.comparison = comparison
        super().__init__(f"Regression gate blocked promotion: {comparison.reason}.")


def timestamp(value):
    aware = value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    return aware.astimezone(datetime.timezone.utc).isoformat()


def evaluation_digest(row):
    """Bind every persisted evaluation field, without reparsing legacy contracts."""
    return evidence_hash({column.name: timestamp(getattr(row, column.name)) if column.name == "evaluated_at"
        else getattr(row, column.name) for column in row.__table__.columns})


def version_configuration_digest(row):
    # An integrity reference to the already verified canonical format-3 source;
    # lets governed suite evolution inspect history without relaxing the registry.
    governance = {"status", "evaluation_id", "published_at", "published_by", "created_at"}
    return evidence_hash({c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in governance})


class BenchRegressionRepository:
    def __init__(self, session, signer, permission_engine=None, approval_authority=None):
        self.session = session
        self.signer = signer
        self.db = DatabaseManager(session.get_bind(), evidence_signer=signer)
        self.bench = BenchRepository(session, signer)
        self.agents = AgentRepository(session)
        self.audit = AuditLogger(self.db)
        self.permissions = permission_engine or PermissionEngine(self.db)
        self.approval_authority = approval_authority or self.bench.approval_authority()

    def scope(self, context, blueprint_id, lock=False):
        blueprint = self.agents.get_blueprint(context, blueprint_id)
        if lock:
            blueprint = self.session.query(type(blueprint)).filter_by(id=blueprint_id).with_for_update().populate_existing().one()
        return blueprint

    def receipt(self, context, baseline_id, blueprint_id=None):
        row = self.session.get(BenchBaselineModel, baseline_id)
        if row is None:
            raise QualityGateFailedError("Accepted baseline reference is missing.")
        if ((row.organization_id, row.project_id) != (context.organization_id, context.project_id)
                or blueprint_id is not None and row.blueprint_id != blueprint_id):
            raise TenantIsolationError("Accepted baseline scope differs.")
        try:
            baseline = AcceptedBaseline.model_validate_json(row.details_json)
            bindings = {"id": baseline.baseline_id, "organization_id": baseline.organization_id,
                "project_id": baseline.project_id, "blueprint_id": baseline.blueprint_id, "generation": baseline.generation,
                "evaluation_id": baseline.evaluation.evaluation_id, "version_id": baseline.evaluation.version_id,
                "payload_hash": baseline.evaluation.payload_hash, "suite_id": baseline.suite_id,
                "evaluation_version": baseline.evaluation_version, "suite_hash": baseline.suite_hash,
                "accepted_by": baseline.accepted_by, "supersedes_id": baseline.supersedes_id}
            if (any(getattr(row, key) != value for key, value in bindings.items())
                    or timestamp(row.accepted_at) != baseline.accepted_at
                    or baseline.attestation != row.attestation
                    or not self.signer.verify("bench_baseline", baseline.model_dump(mode="json", exclude={"attestation"}), row.attestation)):
                raise ValueError("Baseline receipt differs.")
            evaluation = self.bench.get_evaluation(context, baseline.evaluation.evaluation_id)
            version = self.session.get(AgentVersionModel, baseline.evaluation.version_id)
            if (version is None or version.blueprint_id != baseline.blueprint_id or version.payload_hash != baseline.evaluation.payload_hash
                    or version_configuration_digest(version) != baseline.agent_configuration_hash
                    or evaluation_digest(evaluation) != baseline.evaluation.evidence_hash):
                raise ValueError("Accepted evaluation has changed.")
            return baseline
        except (ValueError, TypeError) as exc:
            raise QualityGateFailedError("Accepted baseline integrity is invalid.") from exc

    def current(self, context, blueprint_id, lock=False):
        blueprint = self.scope(context, blueprint_id, lock)
        newest = self.session.query(BenchBaselineModel).filter_by(organization_id=context.organization_id,
            project_id=context.project_id, blueprint_id=blueprint_id).order_by(BenchBaselineModel.generation.desc()).first()
        if blueprint.bench_baseline_id is None:
            if newest:
                raise QualityGateFailedError("Baseline history exists but current authority is missing.")
            return None
        baseline = self.receipt(context, blueprint.bench_baseline_id, blueprint_id)
        if newest is None or newest.id != baseline.baseline_id:
            raise QualityGateFailedError("Current baseline does not match the latest accepted generation.")
        cursor, seen = baseline, set()
        while cursor.supersedes_id:
            if cursor.baseline_id in seen:
                raise QualityGateFailedError("Baseline history contains a cycle.")
            seen.add(cursor.baseline_id)
            prior = self.receipt(context, cursor.supersedes_id, blueprint_id)
            if prior.generation + 1 != cursor.generation or evidence_hash(prior.model_dump(mode="json")) != cursor.previous_hash:
                raise QualityGateFailedError("Baseline history binding differs.")
            cursor = prior
        if cursor.generation != 1 or cursor.previous_hash:
            raise QualityGateFailedError("Baseline history origin is invalid.")
        return baseline

    @staticmethod
    def identity(row, version, evidence_format):
        return EvaluationIdentity(evaluation_id=row.id, version_id=version.id, version_number=version.version_number,
            payload_hash=version.payload_hash, evidence_hash=evaluation_digest(row), evidence_format=evidence_format)

    def compare(self, context, version_id, evaluation_id=None, persist=False):
        stored_version = self.agents.get_version(context, version_id, for_update=persist)
        version = AgentVersion.from_stored(stored_version)
        row = self.bench.get_evaluation(context, evaluation_id or version.evaluation_id)
        if row.version_id != version_id or row.blueprint_id != version.blueprint_id:
            raise TenantIsolationError("Candidate evaluation version/blueprint differs.")
        baseline_error = None
        try:
            baseline = self.current(context, version.blueprint_id, lock=persist)
        except QualityGateFailedError as exc:
            baseline, baseline_error = None, str(exc)
        suite = get_bench_suite(version.evaluation_reference.suite_id)
        candidate, validation_error = None, None
        try:
            candidate = self.bench.validate_stored(context, row, version)
        except (QualityGateFailedError, ValueError, TypeError) as exc:
            validation_error = str(exc)
        identity = self.identity(row, version, candidate.evidence_format if candidate else 2)
        published_history = self.session.query(AgentVersionModel).filter_by(blueprint_id=version.blueprint_id).filter(
            (AgentVersionModel.published_at.isnot(None)) | AgentVersionModel.status.in_(["published", "deprecated"])).count() > 0
        fingerprint = evidence_hash({"baseline": baseline.model_dump(mode="json") if baseline else None,
            "candidate": identity.model_dump(mode="json"), "suite_hash": suite.suite_hash,
            "history": published_history, "baseline_error": baseline_error, "current_evaluation_id": version.evaluation_id})
        comparison_id = "cmp_" + fingerprint[:60]
        cached = self.session.get(BenchComparisonModel, comparison_id)
        compared_at = timestamp(cached.compared_at) if cached else timestamp(datetime.datetime.now(datetime.timezone.utc))
        comparison = RegressionComparison(comparison_id=comparison_id, organization_id=context.organization_id,
            project_id=context.project_id, blueprint_id=version.blueprint_id, baseline_id=baseline.baseline_id if baseline else None,
            baseline=baseline.evaluation if baseline else None, candidate=identity, suite_id=suite.suite_id,
            evaluation_version=suite.evaluation_version, suite_hash=suite.suite_hash, compared_at=compared_at,
            state="bootstrap", reason="initial_publication_bootstrap", promotion_blocked=False,
            candidate_score=candidate.score if candidate else None, limitations=baseline.limitations if baseline else [])
        if baseline_error or validation_error:
            block(comparison, "invalid", "baseline_integrity_invalid" if baseline_error else "candidate_evidence_invalid")
        elif row.id != version.evaluation_id:
            block(comparison, "invalid", "candidate_evaluation_not_current")
        elif baseline is None:
            if published_history:
                block(comparison, "baseline_required", "published_history_requires_baseline")
        elif ((baseline.suite_id, baseline.evaluation_version, baseline.suite_hash, baseline.evaluation.evidence_format)
                != (suite.suite_id, candidate.evaluation_version, candidate.suite_hash, candidate.evidence_format)
                or baseline.suite_definition.suite_hash != suite.suite_hash):
            block(comparison, "incompatible", "suite_or_evidence_format_changed")
        else:
            try:
                prior_version = AgentVersion.from_stored(self.agents.get_version(context, baseline.evaluation.version_id))
                prior = self.bench.validate_stored(context, self.bench.get_evaluation(context, baseline.evaluation.evaluation_id), prior_version)
                # Canonical aliases are resolved before comparison, including legacy records.
                comparison = compare_evaluations(comparison, prior.model_copy(update={"suite_id": suite.suite_id}),
                    candidate.model_copy(update={"suite_id": suite.suite_id}), suite)
            except (QualityGateFailedError, ValueError, TypeError):
                block(comparison, "invalid", "baseline_evidence_invalid")
        if candidate is not None and not candidate.passed and not comparison.promotion_blocked:
            comparison.promotion_blocked = True
            comparison.reason = "candidate_quality_gate_failed"
        if cached:
            try:
                self.validate_cached(context, cached, comparison)
            except QualityGateFailedError:
                block(comparison, "invalid", "comparison_integrity_invalid")
                comparison.comparison_id = "cmp_" + evidence_hash({"comparison_id": comparison_id,
                    "stored_details": cached.details_json, "stored_attestation": cached.attestation})[:60]
                comparison_id = comparison.comparison_id
                cached = self.session.get(BenchComparisonModel, comparison_id)
                if cached:
                    self.validate_cached(context, cached, comparison)
            if cached:
                comparison.attestation = cached.attestation
        if not cached and persist:
            comparison.attestation = self.signer.sign("bench_regression", comparison.model_dump(mode="json", exclude={"attestation"}))
            self.session.add(BenchComparisonModel(id=comparison_id, organization_id=context.organization_id,
                project_id=context.project_id, blueprint_id=version.blueprint_id, baseline_id=comparison.baseline_id,
                candidate_evaluation_id=row.id, compared_at=datetime.datetime.fromisoformat(compared_at),
                details_json=comparison.model_dump_json(), attestation=comparison.attestation))
            self.session.flush()
            payload = {"comparison_id": comparison_id, "baseline_id": comparison.baseline_id,
                "candidate_evaluation_id": row.id, "state": comparison.state,
                "critical_count": len(comparison.critical_regressions), "reason": comparison.reason}
            self.audit.record("bench.regression.compared", context, version_id, AuditStatus.COMPLETED, payload, session=self.session)
            if comparison.critical_regressions:
                self.audit.record("bench.regression.critical", context, version_id, AuditStatus.FAILED, payload, session=self.session)
            if comparison.promotion_blocked:
                self.audit.record("bench.promotion.blocked", context, version_id, AuditStatus.DENIED, payload, session=self.session)
        self.session.info.setdefault("bench_comparisons", {})[version_id] = comparison
        return comparison

    def validate_cached(self, context, row, expected):
        try:
            stored = RegressionComparison.model_validate_json(row.details_json)
            if ((row.organization_id, row.project_id, row.blueprint_id, row.baseline_id, row.candidate_evaluation_id)
                    != (context.organization_id, context.project_id, expected.blueprint_id, expected.baseline_id, expected.candidate.evaluation_id)
                    or stored.comparison_id != row.id or timestamp(row.compared_at) != stored.compared_at
                    or stored.attestation != row.attestation
                    or not self.signer.verify("bench_regression", stored.model_dump(mode="json", exclude={"attestation"}), row.attestation)
                    or stored.model_dump(exclude={"attestation"}) != expected.model_dump(exclude={"attestation"})):
                raise ValueError("Comparison differs from recomputation.")
        except (ValueError, TypeError) as exc:
            raise QualityGateFailedError("Persisted regression comparison is invalid or stale.") from exc

    def verify_current_comparison(self, context, comparison_id):
        row = self.session.get(BenchComparisonModel, comparison_id)
        if row is None or (row.organization_id, row.project_id) != (context.organization_id, context.project_id):
            raise TenantIsolationError("Regression comparison scope differs or is missing.")
        stored = RegressionComparison.model_validate_json(row.details_json)
        current = self.compare(context, stored.candidate.version_id, persist=False)
        if current.comparison_id != comparison_id:
            raise QualityGateFailedError("Regression comparison is stale; obtain a new human approval.")
        self.validate_cached(context, row, current)
        return current

    def enforce(self, context, version_id):
        comparison = self.compare(context, version_id, persist=self.session.info.get("write", False))
        if comparison.promotion_blocked:
            raise RegressionGateFailedError(comparison)
        return comparison

    def verify_publication_comparison(self, context, comparison_id, version):
        """Revalidate frozen publication evidence without requiring today's baseline."""
        row = self.session.get(BenchComparisonModel, comparison_id)
        if row is None:
            raise QualityGateFailedError("Publication comparison is missing.")
        stored = RegressionComparison.model_validate_json(row.details_json)
        candidate_row = self.bench.get_evaluation(context, version.evaluation_id)
        candidate = self.bench.validate_stored(context, candidate_row, version)
        if stored.candidate != self.identity(candidate_row, version, candidate.evidence_format):
            raise QualityGateFailedError("Publication candidate evidence changed.")
        suite = get_bench_suite(version.evaluation_reference.suite_id)
        if (stored.suite_id, stored.evaluation_version, stored.suite_hash) != (suite.suite_id, suite.evaluation_version, suite.suite_hash):
            raise QualityGateFailedError("Publication evaluator configuration is no longer supported.")
        expected = stored.model_copy(update={"state": "bootstrap", "reason": "initial_publication_bootstrap",
            "promotion_blocked": False, "baseline_score": None, "candidate_score": candidate.score,
            "score_delta": None, "scenarios": [], "metrics": {}, "provenance_differences": {},
            "regressions": [], "critical_regressions": []})
        if stored.baseline_id:
            baseline = self.receipt(context, stored.baseline_id, version.blueprint_id)
            if stored.baseline != baseline.evaluation:
                raise QualityGateFailedError("Publication baseline identity changed.")
            prior_version = AgentVersion.from_stored(self.agents.get_version(context, baseline.evaluation.version_id))
            prior = self.bench.validate_stored(context, self.bench.get_evaluation(context, baseline.evaluation.evaluation_id), prior_version)
            expected = compare_evaluations(expected, prior.model_copy(update={"suite_id": suite.suite_id}),
                candidate.model_copy(update={"suite_id": suite.suite_id}), suite)
        elif stored.baseline is not None:
            raise QualityGateFailedError("Publication bootstrap has an unexpected baseline.")
        self.validate_cached(context, row, expected)
        if expected.promotion_blocked:
            raise QualityGateFailedError("Publication comparison does not permit promotion.")
        return stored

    def accept(self, context, evaluation_id, *, expected_baseline_id=None, reason, transition=False, approval=None):
        action = "version:publish" if approval else "bench:accept_baseline"
        self.permissions.enforce(action, context, context.organization_id, context.project_id)
        if context.actor.actor_type != ActorType.USER:
            raise PermissionDeniedError("Baseline acceptance requires a human actor.")
        if not reason.strip():
            raise QualityGateFailedError("Baseline acceptance requires a governance reason.")
        row = self.bench.get_evaluation(context, evaluation_id)
        self.scope(context, row.blueprint_id, lock=True)
        version_row = self.agents.get_version(context, row.version_id, for_update=True)
        version = AgentVersion.from_stored(version_row)
        current = self.current(context, row.blueprint_id)
        if (current.baseline_id if current else None) != expected_baseline_id:
            raise QualityGateFailedError("Baseline changed; review the current baseline before acceptance.")
        result = self.bench.validate_stored(context, row, version)
        if version.canonical_format != 3 or version.evaluation_id != evaluation_id:
            raise QualityGateFailedError("Baseline requires current canonical payload and evaluation reference.")
        latest = self.session.query(type(row)).filter_by(organization_id=context.organization_id,
            project_id=context.project_id, version_id=version.id).order_by(type(row).evaluated_at.desc(), type(row).id.desc()).first()
        if latest.id != evaluation_id:
            raise QualityGateFailedError("Baseline requires the latest evaluation.")
        BenchQualityGate().enforce(result, version.evaluation_reference, signer=self.signer,
            approval_authority=self.bench.approval_authority())
        if current and current.evaluation.evaluation_id == evaluation_id:
            return current
        comparison = self.compare(context, version.id, persist=True)
        suite = get_bench_suite(result.suite_id)
        if transition:
            if (approval or current is None or comparison.state != "incompatible"
                    or comparison.reason != "suite_or_evidence_format_changed"):
                raise QualityGateFailedError("Suite transition requires an existing incompatible baseline and explicit admin acceptance.")
        elif comparison.promotion_blocked:
            # A verified historical publication may initialize a missing baseline after upgrade.
            if not (current is None and version_row.status in {"published", "deprecated"}
                    and comparison.state == "baseline_required" and not approval):
                raise RegressionGateFailedError(comparison)
            self.approval_authority.verify_approval(context, "agent_version", version.id, version.payload_hash, session=self.session)
        member = self.session.query(MembershipModel).filter_by(organization_id=context.organization_id,
            user_id=context.actor.actor_id).with_for_update().first()
        if (not member or member.status != "active" or member.role not in ({"admin", "operator"} if approval else {"admin"})):
            raise PermissionDeniedError("Baseline actor lacks current authority.")
        accepted_by = context.actor.actor_id
        if approval:
            self.approval_authority.verify_record(approval)
            if (approval.target_type != "agent_version" or approval.target_id != version.id
                    or approval.payload_hash != version.payload_hash or approval.evaluation_id != evaluation_id
                    or approval.regression_comparison_id != comparison.comparison_id):
                raise QualityGateFailedError("Publication acceptance differs from reviewed evidence.")
            accepted_by = approval.approved_by
        baseline = AcceptedBaseline(baseline_id="base_" + uuid.uuid4().hex, organization_id=context.organization_id,
            project_id=context.project_id, blueprint_id=row.blueprint_id, generation=current.generation + 1 if current else 1,
            evaluation=self.identity(row, version, result.evidence_format), suite_id=suite.suite_id,
            agent_configuration_hash=version_configuration_digest(version_row),
            evaluation_version=result.evaluation_version, suite_hash=result.suite_hash, accepted_by=accepted_by,
            accepted_at=timestamp(datetime.datetime.now(datetime.timezone.utc)),
            acceptance="publication" if approval else "suite_transition" if transition else "explicit", reason=reason.strip(),
            approval_id=approval.approval_id if approval else None, supersedes_id=current.baseline_id if current else None,
            previous_hash=evidence_hash(current.model_dump(mode="json")) if current else None, suite_definition=suite,
            limitations=["legacy_scenario_evidence_only", "grader_comparison_unavailable", "cost_resources_unavailable"] if result.evidence_format == 1 else [])
        baseline.attestation = self.signer.sign("bench_baseline", baseline.model_dump(mode="json", exclude={"attestation"}))
        self.session.add(BenchBaselineModel(id=baseline.baseline_id, organization_id=context.organization_id,
            project_id=context.project_id, blueprint_id=row.blueprint_id, generation=baseline.generation,
            evaluation_id=evaluation_id, version_id=version.id, payload_hash=version.payload_hash, suite_id=baseline.suite_id,
            evaluation_version=baseline.evaluation_version, suite_hash=baseline.suite_hash, accepted_by=accepted_by,
            accepted_at=datetime.datetime.fromisoformat(baseline.accepted_at), supersedes_id=baseline.supersedes_id,
            details_json=baseline.model_dump_json(), attestation=baseline.attestation))
        self.scope(context, row.blueprint_id).bench_baseline_id = baseline.baseline_id
        self.session.flush()
        payload = {"baseline_id": baseline.baseline_id, "evaluation_id": evaluation_id, "generation": baseline.generation,
            "previous_baseline_id": baseline.supersedes_id, "suite_id": baseline.suite_id,
            "payload_hash": version.payload_hash, "accepted_by": accepted_by, "acceptance": baseline.acceptance}
        if current:
            self.audit.record("bench.baseline.superseded", context, current.baseline_id, AuditStatus.COMPLETED, payload, session=self.session)
        self.audit.record("bench.baseline.accepted", context, baseline.baseline_id, AuditStatus.ALLOWED, payload, session=self.session)
        return baseline
