"""Core human approval authority with scoped, durable evidence attestations."""

import datetime
import uuid
from contextlib import nullcontext
from typing import Optional

from database.connection import DatabaseManager
from database.repositories.agent_repo import AgentRepository
from database.repositories.approval_repo import ApprovalRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.exceptions import InvalidStateTransitionError
from database.schema import ApprovalModel, MembershipModel
from modules.core.audit.logger import AuditLogger
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from packages.contracts.approval import ApprovalRecord
from packages.contracts.core import ActorType, AuditStatus, SecurityContext


class ApprovalRequiredError(Exception):
    pass


class UnauthorizedApproverError(Exception):
    pass


class PayloadHashMismatchError(Exception):
    pass


class ApprovalEngine:
    def __init__(self, db_manager: DatabaseManager, audit_logger=None, permission_engine=None):
        self.db_manager = db_manager
        self.audit_logger = audit_logger or AuditLogger(db_manager=db_manager)
        self.permission_engine = permission_engine or PermissionEngine(db_manager=db_manager)

    @staticmethod
    def contract(row):
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        return ApprovalRecord(
            approval_id=row.id, organization_id=row.organization_id, project_id=row.project_id,
            target_type=row.target_type, target_id=row.target_id, payload_hash=row.payload_hash,
            approved_by=row.approved_by, status=row.status, comments=row.comments,
            created_at=created_at.isoformat(), evaluation_id=row.evaluation_id,
            attestation=row.attestation or "",
        )

    def verify_signature(self, row):
        return self.verify_record(self.contract(row))

    def verify_record(self, record):
        """Verify a captured approval through existing durable Core authority."""
        with self.db_manager.session() as session:
            stored = session.get(ApprovalModel, record.approval_id)
            if stored is None or self.contract(stored) != record:
                raise ApprovalRequiredError("Approval no longer matches current Core evidence.")
        payload = record.model_dump(mode="json", exclude={"attestation"})
        if not self.db_manager.evidence_signer.verify("human_approval", payload, record.attestation):
            raise ApprovalRequiredError("Approval provenance is not verified.")
        approver = self.permission_engine.identity_binder.create_trusted_context(
            record.approved_by, record.organization_id, record.project_id)
        try:
            self.permission_engine.enforce("version:approve", approver, record.organization_id, record.project_id)
        except PermissionDeniedError as exc:
            raise ApprovalRequiredError("Human approver no longer has valid authority.") from exc
        return record

    def current_evidence(self, context, target_type, target_id, payload_hash, session):
        if target_type != "agent_version":
            return None
        version = AgentRepository(session).get_version(context, target_id, for_update=True)
        if version.payload_hash != payload_hash:
            raise PayloadHashMismatchError("Actual configuration differs from reviewed payload hash.")
        if version.status not in {"draft", "approved", "published"}:
            raise InvalidStateTransitionError("Human approval requires finished Bench evidence.")
        evidence = BenchRepository(session, self.db_manager.evidence_signer).get_latest_passing_evaluation(context, target_id)
        if evidence is None:
            from modules.bench.quality_gate import QualityGateFailedError
            raise QualityGateFailedError("No current passing Bench evaluation found.")
        return evidence.id

    def grant_approval(self, context: SecurityContext, target_type: str, target_id: str,
                       payload_hash: str, comments: Optional[str] = None, session=None) -> ApprovalRecord:
        if context.actor.actor_type != ActorType.USER:
            reason = "Agents cannot grant approvals or self-publish." if context.actor.actor_type == ActorType.AGENT else "Only human users can grant approvals."
            raise UnauthorizedApproverError(reason)
        try:
            self.permission_engine.enforce("version:approve", context, context.organization_id, context.project_id)
        except PermissionDeniedError as exc:
            raise UnauthorizedApproverError(f"Actor lacks 'admin' role required to grant approvals: {exc}") from exc
        with (nullcontext(session) if session is not None else self.db_manager.session(write=True)) as active:
            # All governance writers lock version before membership to avoid lock inversion.
            evaluation_id = self.current_evidence(context, target_type, target_id, payload_hash, active)
            member = active.query(MembershipModel).filter_by(
                organization_id=context.organization_id, user_id=context.actor.actor_id,
            ).with_for_update().first()
            if not member or member.role != "admin" or member.status != "active":
                raise UnauthorizedApproverError("Human approver requires active admin authority at commit time.")
            if target_type == "agent_version":
                version = AgentRepository(active).get_version(context, target_id)
                if version.status == "published":
                    raise InvalidStateTransitionError("Published versions cannot receive new approval.")
            repo = ApprovalRepository(active)
            existing = repo.get_approval(context, target_type, target_id, payload_hash, evaluation_id)
            if existing:
                try:
                    return self.verify_signature(existing)
                except ApprovalRequiredError:
                    # A fresh, authorized human decision does not rewrite stale evidence.
                    pass
            row = repo.record_approval(context, f"appr_{uuid.uuid4().hex}", target_type,
                                       target_id, payload_hash, context.actor.actor_id,
                                       comments=comments, evaluation_id=evaluation_id)
            record = self.contract(row)
            row.attestation = self.db_manager.evidence_signer.sign(
                "human_approval", record.model_dump(mode="json", exclude={"attestation"}))
            active.flush()
            self.audit_logger.record("core.approval.granted", context, target_id, AuditStatus.ALLOWED,
                                     {"target_type": target_type, "payload_hash": payload_hash,
                                      "approved_by": context.actor.actor_id, "evaluation_id": evaluation_id}, session=active)
            return self.contract(row)

    def verify_approval(self, context: SecurityContext, target_type: str, target_id: str,
                        expected_payload_hash: str, session=None) -> ApprovalRecord:
        self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
        with (nullcontext(session) if session is not None else self.db_manager.session()) as active:
            evaluation_id = self.current_evidence(context, target_type, target_id, expected_payload_hash, active)
            approval = ApprovalRepository(active).get_approval(context, target_type, target_id, expected_payload_hash, evaluation_id)
            if approval is None:
                different = active.query(ApprovalModel).filter_by(
                    organization_id=context.organization_id, project_id=context.project_id,
                    target_type=target_type, target_id=target_id, status="approved").first()
                if different and different.payload_hash != expected_payload_hash:
                    raise PayloadHashMismatchError("Modification after approval is forbidden.")
                raise ApprovalRequiredError("No current human approval bound to this configuration and Bench evaluation.")
            return self.verify_signature(approval)
