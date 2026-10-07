"""Derived version registry and governed assignment activation over existing authority."""
from __future__ import annotations

import datetime
import json
import uuid

from database.connection import DatabaseManager
from database.repositories.agent_repo import AgentRepository
from database.repositories.approval_repo import ApprovalRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.bench_regression_repo import BenchRegressionRepository, evaluation_digest, timestamp
from database.repositories.exceptions import InvalidStateTransitionError, TenantIsolationError, RepositoryError
from database.schema import (AgentAssignmentModel, AgentPublicationModel, AgentVersionModel,
    AssignmentTransitionModel, AuditEventModel, BenchBaselineModel, MembershipModel)
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.approvals.engine import ApprovalEngine, ApprovalRequiredError, PayloadHashMismatchError
from modules.core.audit.logger import AuditLogger
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.workflows.coordinator import IdempotencyConflictError
from packages.contracts.agent import (AgentVersion, AssignmentTransition, PublicationEvidence, RollbackIntent,
    VersionIntegrityError, VersionRegistryEntry)
from packages.contracts.bench import evidence_hash
from packages.contracts.core import ActorType, AuditEvent, AuditStatus


class AgentActivationRepository:
    def __init__(self, session, signer, permission_engine=None):
        self.session = session
        self.signer = signer
        self.db = DatabaseManager(session.get_bind(), evidence_signer=signer)
        self.agents = AgentRepository(session)
        self.permissions = permission_engine or PermissionEngine(self.db)
        self.approvals = ApprovalEngine(self.db, permission_engine=self.permissions)
        self.bench = BenchRepository(session, signer)
        self.regression = BenchRegressionRepository(session, signer, self.permissions, self.approvals)
        self.audit = AuditLogger(self.db)

    def publication_sources(self, context, version_id, baseline_id=None):
        row = self.agents.get_version(context, version_id)
        version = AgentVersion.from_stored(row)
        version.verify_integrity(require_canonical=True)
        if version.status.value != "published" or not row.published_at or not row.published_by:
            raise InvalidStateTransitionError("Rollback target requires a previously published version.")
        evaluation = self.bench.get_latest_passing_evaluation(context, version.id)
        if evaluation is None:
            raise QualityGateFailedError("Publication Bench evidence is not verified.")
        approval = self.approvals.verify_approval(context, "agent_version", version.id, version.payload_hash, session=self.session)
        if baseline_id is None:
            baseline_row = self.session.query(BenchBaselineModel).filter_by(organization_id=context.organization_id,
                project_id=context.project_id, blueprint_id=version.blueprint_id, evaluation_id=evaluation.id).order_by(
                BenchBaselineModel.generation.asc()).first()
            if baseline_row is None:
                raise QualityGateFailedError("Publication has no accepted baseline provenance.")
            baseline_id = baseline_row.id
        baseline = self.regression.receipt(context, baseline_id, version.blueprint_id)
        if baseline.evaluation.evaluation_id != evaluation.id or baseline.evaluation.version_id != version.id:
            raise QualityGateFailedError("Publication baseline does not bind this version.")
        cursor = baseline
        while cursor.supersedes_id:
            prior = self.regression.receipt(context, cursor.supersedes_id, version.blueprint_id)
            if prior.generation + 1 != cursor.generation or evidence_hash(prior.model_dump(mode="json")) != cursor.previous_hash:
                raise QualityGateFailedError("Publication baseline chain is invalid.")
            cursor = prior
        if cursor.generation != 1 or cursor.previous_hash:
            raise QualityGateFailedError("Publication baseline origin is invalid.")
        comparison = (self.regression.verify_publication_comparison(context, approval.regression_comparison_id, version)
            if approval.regression_comparison_id else None)
        publisher = self.permissions.identity_binder.create_trusted_context(row.published_by, context.organization_id, context.project_id)
        self.permissions.enforce("version:publish", publisher, context.organization_id, context.project_id)
        if publisher.actor.actor_type != ActorType.USER:
            raise PermissionDeniedError("Publication must have a human publisher.")
        return row, evaluation, approval, baseline, comparison

    def publication_contract(self, context, sources, publication_id):
        row, evaluation, approval, baseline, comparison = sources
        return PublicationEvidence(publication_id=publication_id, organization_id=context.organization_id,
            project_id=context.project_id, blueprint_id=row.blueprint_id, version_id=row.id, payload_hash=row.payload_hash,
            evaluation_id=evaluation.id, evaluation_hash=evaluation_digest(evaluation), approval_id=approval.approval_id,
            approval_hash=evidence_hash(approval.model_dump(mode="json")), baseline_id=baseline.baseline_id,
            baseline_hash=evidence_hash(baseline.model_dump(mode="json")),
            comparison_id=comparison.comparison_id if comparison else None,
            comparison_hash=evidence_hash(comparison.model_dump(mode="json")) if comparison else None,
            published_by=row.published_by, published_at=timestamp(row.published_at))

    def record_publication(self, context, version_id, baseline_id):
        if self.session.info.get("publishing_version_id") != version_id:
            raise InvalidStateTransitionError("Publication receipt requires the governed Factory publication transaction.")
        sources = self.publication_sources(context, version_id, baseline_id)
        contract = self.publication_contract(context, sources, "pub_" + uuid.uuid4().hex)
        contract.attestation = self.signer.sign("agent_publication", contract.model_dump(mode="json", exclude={"attestation"}))
        self.session.add(AgentPublicationModel(id=contract.publication_id, organization_id=context.organization_id,
            project_id=context.project_id, blueprint_id=contract.blueprint_id, version_id=version_id,
            details_json=contract.model_dump_json(), attestation=contract.attestation))
        self.session.flush()
        self.session.info.pop("publishing_version_id", None)
        return contract

    def known_good(self, context, version_id):
        receipt = self.session.query(AgentPublicationModel).filter_by(version_id=version_id).first()
        sources = self.publication_sources(context, version_id,
            PublicationEvidence.model_validate_json(receipt.details_json).baseline_id if receipt else None)
        if receipt:
            stored = PublicationEvidence.model_validate_json(receipt.details_json)
            expected = self.publication_contract(context, sources, receipt.id)
            if ((receipt.organization_id, receipt.project_id, receipt.blueprint_id, receipt.version_id)
                    != (context.organization_id, context.project_id, expected.blueprint_id, version_id)
                    or stored.model_dump(exclude={"attestation"}) != expected.model_dump(exclude={"attestation"})
                    or stored.attestation != receipt.attestation or not self.signer.verify("agent_publication",
                        expected.model_dump(mode="json", exclude={"attestation"}), receipt.attestation)):
                raise VersionIntegrityError("Publication receipt does not match verified historical authority.")
            return {"publication": stored.model_dump(mode="json"), "limitations": []}
        # Pre-migration publications remain derived from actual signed governance and
        # their existing publication audit. No migration invents publication receipts.
        row, _, approval, baseline, _ = sources
        events = self.session.query(AuditEventModel).filter_by(organization_id=context.organization_id,
            project_id=context.project_id, resource_id=version_id, event_type="factory.version.published").all()
        for event in events:
            payload = json.loads(event.redacted_payload_json)
            contract = AuditEvent(event_id=event.event_id, event_type=event.event_type, schema_version=event.schema_version,
                occurred_at=timestamp(event.occurred_at), organization_id=event.organization_id, project_id=event.project_id,
                actor_type=event.actor_type, actor_id=event.actor_id, correlation_id=event.correlation_id,
                resource_id=event.resource_id, causation_id=event.causation_id, status=event.status,
                redacted_payload=payload, integrity_reference=event.integrity_reference)
            if (contract.calculate_integrity() == event.integrity_reference and event.actor_type == "user"
                    and event.actor_id == row.published_by and event.status == "completed"
                    and payload.get("payload_hash") == row.payload_hash and payload.get("blueprint_id") == row.blueprint_id
                    and payload.get("baseline_id") == baseline.baseline_id
                    and baseline.acceptance == "publication" and baseline.approval_id == approval.approval_id):
                return {"publication": self.publication_contract(context, sources, "legacy_" + event.id).model_dump(mode="json"),
                    "legacy_audit_hash": event.integrity_reference, "limitations": ["historical_publication_audit", "no_signed_publication_receipt"]}
        raise QualityGateFailedError("Historical publication cannot be proved; baseline acceptance alone is insufficient.")

    def registry_entry(self, context, row):
        entry = VersionRegistryEntry(version_id=row.id, blueprint_id=row.blueprint_id, version_number=row.version_number,
            status=row.status, payload_hash=row.payload_hash, created_at=timestamp(row.created_at),
            published_at=timestamp(row.published_at) if row.published_at else None, published_by=row.published_by,
            evaluation_id=row.evaluation_id, active_assignment_count=self.session.query(AgentAssignmentModel).filter_by(
                organization_id=context.organization_id, project_id=context.project_id, version_id=row.id, status="active").count())
        try:
            current_id = self.agents.get_blueprint(context, row.blueprint_id).bench_baseline_id
            if current_id:
                current = self.regression.receipt(context, current_id, row.blueprint_id)
                entry.current_baseline = current.evaluation.version_id == row.id
        except (ValueError, RepositoryError, QualityGateFailedError):
            pass
        try:
            version = AgentVersion.from_stored(row)
            version.verify_integrity(require_canonical=True)
            if row.evaluation_id:
                evaluation = self.bench.validate_stored(context, self.bench.get_evaluation(context, row.evaluation_id), version)
                entry.bench_verified, entry.bench_passed = True, evaluation.passed
                approval_row = ApprovalRepository(self.session).get_approval(context, "agent_version", row.id,
                    row.payload_hash, row.evaluation_id)
                if approval_row:
                    approval = self.approvals.verify_signature(approval_row)
                    entry.approval_id, entry.approval_status = approval.approval_id, approval.status
                    entry.regression_comparison_id = approval.regression_comparison_id
            if row.status != "published":
                entry.reason = "version_not_published" if row.status != "deprecated" else "deprecated_version_is_terminal"
                return entry
            reference = self.known_good(context, row.id)
            publication = reference["publication"]
            entry.bench_verified = entry.rollback_eligible = True
            entry.reason = "verified_historical_publication"
            for key in ("approval_id", "baseline_id", "publication_id"):
                setattr(entry, key, publication[key])
            entry.approval_status = "approved"
            entry.regression_comparison_id = publication["comparison_id"]
            entry.limitations = reference["limitations"]
        except (ValueError, RuntimeError, RepositoryError, QualityGateFailedError, PermissionDeniedError,
                ApprovalRequiredError, PayloadHashMismatchError) as exc:
            # Read-only registry must represent corrupt/legacy history, never grant it.
            entry.reason = type(exc).__name__
        return entry

    @staticmethod
    def assignment_digest(row):
        return evidence_hash({key: getattr(row, key) for key in ("id", "organization_id", "project_id", "division_id",
            "blueprint_id", "role_name")})

    def lock_assignment(self, context, assignment_id):
        row = self.agents.get_assignment(context, assignment_id)
        self.regression.scope(context, row.blueprint_id, lock=True)
        return self.session.query(AgentAssignmentModel).filter_by(id=assignment_id).with_for_update().populate_existing().one()

    def history(self, context, assignment):
        rows = self.session.query(AssignmentTransitionModel).filter_by(organization_id=context.organization_id,
            project_id=context.project_id, assignment_id=assignment.id).order_by(AssignmentTransitionModel.generation.asc()).all()
        transitions, prior = [], None
        for row in rows:
            value = AssignmentTransition.model_validate_json(row.details_json)
            bindings = {"id": value.transition_id, "organization_id": value.organization_id, "project_id": value.project_id,
                "assignment_id": value.assignment_id, "blueprint_id": value.blueprint_id, "generation": value.generation,
                "from_version_id": value.from_version_id, "to_version_id": value.to_version_id,
                "transition_type": value.transition_type, "actor_id": value.actor_id, "idempotency_key": value.idempotency_key}
            if (any(getattr(row, k) != v for k, v in bindings.items()) or value.attestation != row.attestation
                    or timestamp(row.committed_at) != value.committed_at
                    or not self.signer.verify("assignment_transition", value.model_dump(mode="json", exclude={"attestation"}), row.attestation)
                    or value.assignment_hash != self.assignment_digest(assignment)
                    or value.generation != len(transitions) + 1
                    or value.previous_transition_id != (prior.transition_id if prior else None)
                    or value.previous_hash != (evidence_hash(prior.model_dump(mode="json")) if prior else None)
                    or prior and value.from_version_id != prior.to_version_id
                    or not prior and (value.from_version_id is not None or value.transition_type not in {"initial", "adoption"})):
                raise VersionIntegrityError("Assignment activation history is invalid.")
            transitions.append(value)
            prior = value
        if (prior and (assignment.current_transition_id != prior.transition_id or assignment.version_id != prior.to_version_id)
                or not prior and (assignment.current_transition_id or assignment.activation_origin != "legacy")):
            raise VersionIntegrityError("Assignment pointer differs from activation history.")
        return transitions

    def append(self, context, assignment, target, kind, reason, reference, prior=None, intent=None):
        self.agents.get_assignment(context, assignment.id)
        if kind not in {"initial", "adoption", "rollback"}:
            raise InvalidStateTransitionError("Unsupported assignment transition.")
        if kind == "adoption":
            if assignment.activation_origin != "legacy" or prior or target != assignment.version_id:
                raise InvalidStateTransitionError("Adoption is only an observed pre-existing assignment origin.")
            self.permissions.enforce("agent:rollback", context, context.organization_id, context.project_id)
        else:
            self.permissions.enforce("agent:rollback" if kind == "rollback" else "agent:assign",
                context, context.organization_id, context.project_id)
            target_row = self.agents.get_version(context, target)
            if target_row.blueprint_id != assignment.blueprint_id or self.known_good(context, target) != reference:
                raise VersionIntegrityError("Activation requires exact verified target publication evidence.")
        if kind == "initial" and (prior or assignment.current_transition_id or assignment.version_id != target):
            raise InvalidStateTransitionError("Initial activation cannot replace an existing assignment.")
        if kind == "rollback":
            if intent is None or prior is None or prior.transition_id != assignment.current_transition_id:
                raise InvalidStateTransitionError("Rollback requires reviewed activation and intent.")
            adopted = prior.transition_type == "adoption" and prior.generation == 1 and assignment.activation_origin == "legacy"
            if (intent.target_version_id != target or intent.expected_current_version_id != assignment.version_id
                    or intent.expected_transition_id != (None if adopted else assignment.current_transition_id)):
                raise InvalidStateTransitionError("Rollback intent differs from current assignment.")
            current_row = self.session.get(AgentVersionModel, assignment.version_id)
            if target == assignment.version_id or current_row.published_at and target_row.published_at >= current_row.published_at:
                raise InvalidStateTransitionError("Rollback requires an earlier publication.")
        now = timestamp(datetime.datetime.now(datetime.timezone.utc))
        value = AssignmentTransition(transition_id="act_" + uuid.uuid4().hex, organization_id=context.organization_id,
            project_id=context.project_id, assignment_id=assignment.id, blueprint_id=assignment.blueprint_id,
            generation=prior.generation + 1 if prior else 1, from_version_id=assignment.version_id if prior else None,
            to_version_id=target, transition_type=kind, actor_id=context.actor.actor_id, reason=reason,
            requested_at=now, committed_at=now, idempotency_key=intent.idempotency_key if intent else None,
            request_hash=evidence_hash({"actor": context.actor.actor_id, "intent": intent.model_dump(mode="json") if intent else None,
                "assignment": assignment.id}), previous_transition_id=prior.transition_id if prior else None,
            previous_hash=evidence_hash(prior.model_dump(mode="json")) if prior else None,
            publication_reference=reference, assignment_hash=self.assignment_digest(assignment))
        value.attestation = self.signer.sign("assignment_transition", value.model_dump(mode="json", exclude={"attestation"}))
        self.session.add(AssignmentTransitionModel(id=value.transition_id, organization_id=context.organization_id,
            project_id=context.project_id, assignment_id=assignment.id, blueprint_id=assignment.blueprint_id,
            generation=value.generation, from_version_id=value.from_version_id, to_version_id=target, transition_type=kind,
            actor_id=value.actor_id, committed_at=datetime.datetime.fromisoformat(now), idempotency_key=value.idempotency_key,
            details_json=value.model_dump_json(), attestation=value.attestation))
        assignment._activation_authorized = True
        assignment.version_id, assignment.current_transition_id = target, value.transition_id
        self.session.flush()
        self.audit.record("factory.assignment.activated", context, assignment.id, AuditStatus.COMPLETED,
            {"transition_id": value.transition_id, "type": kind, "from_version_id": value.from_version_id,
                "to_version_id": target, "publication_id": reference["publication"]["publication_id"], "reason": reason}, session=self.session)
        return value

    def initialize(self, context, assignment):
        reference = self.known_good(context, assignment.version_id)
        return self.append(context, assignment, assignment.version_id, "initial", "Initial operational assignment.", reference)

    def rollback(self, context, assignment_id, intent: RollbackIntent):
        intent = RollbackIntent.model_validate(intent)
        self.permissions.enforce("agent:rollback", context, context.organization_id, context.project_id)
        assignment = self.lock_assignment(context, assignment_id)
        history = self.history(context, assignment)
        digest = evidence_hash({"actor": context.actor.actor_id, "intent": intent.model_dump(mode="json"), "assignment": assignment.id})
        existing = next((x for x in history if x.idempotency_key == intent.idempotency_key), None)
        if existing:
            if existing.request_hash != digest:
                raise IdempotencyConflictError("Rollback key is bound to another actor or intent.")
            if self.known_good(context, existing.to_version_id) != existing.publication_reference:
                raise VersionIntegrityError("Rollback target evidence has changed.")
            return existing
        if (assignment.status != "active" or assignment.version_id != intent.expected_current_version_id
                or assignment.current_transition_id != intent.expected_transition_id):
            raise InvalidStateTransitionError("Assignment changed; review current activation before rollback.")
        current = self.session.get(AgentVersionModel, assignment.version_id)
        if current is None:
            raise InvalidStateTransitionError("Current assignment version is missing.")
        # Blueprint and assignment locks are already held. Reject cross-blueprint
        # targets before acquiring a second blueprint lock.
        target = self.agents.get_version(context, intent.target_version_id)
        if target.blueprint_id != assignment.blueprint_id:
            raise TenantIsolationError("Rollback target belongs to another blueprint.")
        target = self.agents.get_version(context, target.id, for_update=True)
        if target.id == current.id or not target.published_at or current.published_at and target.published_at >= current.published_at:
            raise InvalidStateTransitionError("Rollback requires an earlier publication.")
        reference = self.known_good(context, target.id)
        member = self.session.query(MembershipModel).filter_by(organization_id=context.organization_id,
            user_id=context.actor.actor_id).with_for_update().first()
        if context.actor.actor_type != ActorType.USER or not member or member.status != "active" or member.role != "admin":
            raise PermissionDeniedError("Rollback requires current human admin authority.")
        self.audit.record("factory.assignment.rollback_requested", context, assignment.id, AuditStatus.ALLOWED,
            {"target_version_id": target.id, "expected_current_version_id": intent.expected_current_version_id,
                "reason": intent.reason}, session=self.session)
        if not history:
            # Explicit present-time adoption proves only the observed pointer, never
            # invents earlier activations. Current may be bad; only target is known-good.
            adoption_reference = {"publication": {"publication_id": "unverified_observed_version", "version_id": current.id},
                "limitations": ["pre_existing_assignment_origin", "prior_activations_unknown"]}
            history = [self.append(context, assignment, current.id, "adoption", "Observed pre-existing assignment before rollback.", adoption_reference)]
        value = self.append(context, assignment, target.id, "rollback", intent.reason, reference, prior=history[-1], intent=intent)
        self.audit.record("factory.assignment.rollback_committed", context, assignment.id, AuditStatus.COMPLETED,
            {"transition_id": value.transition_id, "from_version_id": value.from_version_id, "to_version_id": value.to_version_id,
                "reason": intent.reason}, session=self.session)
        return value
