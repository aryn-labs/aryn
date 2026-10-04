"""Authoritative cryptographic approval engine for ARYN infrastructure.

Enforces payload hash binding, admin authorization, human-only approval, and immutable audit trails.
Complies with ARYN-ARCH-001 Section 05 and AGENTS.md rules 4, 7.
"""

from __future__ import annotations

import uuid
from typing import Optional
from packages.contracts.core import ActorType, AuditStatus, SecurityContext
from packages.contracts.approval import ApprovalRecord, ApprovalStatus
from database.connection import DatabaseManager
from database.repositories.approval_repo import ApprovalRepository
from modules.core.audit.logger import AuditLogger


class ApprovalRequiredError(Exception):
    """Raised when an operation requires prior human authorization."""
    pass


class UnauthorizedApproverError(Exception):
    """Raised when an actor lacks authority to grant an approval."""
    pass


class PayloadHashMismatchError(Exception):
    """Raised when a target configuration has mutated away from its approved payload hash."""
    pass


class ApprovalEngine:
    """Authoritative gatekeeper for sensitive actions requiring human approval."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        audit_logger: Optional[AuditLogger] = None,
        permission_engine: Optional[Any] = None,
    ) -> None:
        self.db_manager = db_manager
        self.audit_logger = audit_logger or AuditLogger(db_manager=db_manager)
        from modules.core.permissions.engine import PermissionEngine
        self.permission_engine = permission_engine or PermissionEngine(db_manager=db_manager)

    def grant_approval(
        self,
        context: SecurityContext,
        target_type: str,
        target_id: str,
        payload_hash: str,
        comments: Optional[str] = None,
    ) -> ApprovalRecord:
        """Grants human authorization tied cryptographically to the exact payload hash."""
        # 1. Prevent agent self-approval / privilege escalation (AGENTS.md Rule 7)
        if context.actor.actor_type == ActorType.AGENT:
            self.audit_logger.record(
                event_type="core.approval.denied",
                context=context,
                resource_id=target_id,
                status=AuditStatus.DENIED,
                payload={"reason": "Agents are strictly forbidden from self-approving or self-publishing."},
            )
            raise UnauthorizedApproverError("Agents cannot grant approvals or self-publish.")

        # 2. Enforce admin role and active membership authoritatively via PermissionEngine
        from modules.core.permissions.engine import PermissionDeniedError
        try:
            self.permission_engine.enforce(
                "version:approve",
                context,
                target_org_id=context.organization_id,
                target_project_id=context.project_id,
            )
        except PermissionDeniedError as exc:
            self.audit_logger.record(
                event_type="core.approval.denied",
                context=context,
                resource_id=target_id,
                status=AuditStatus.DENIED,
                payload={"reason": str(exc)},
            )
            raise UnauthorizedApproverError(
                f"Actor '{context.actor.actor_id}' lacks 'admin' role required to grant approvals: {exc}"
            ) from exc

        # 3. Persist approval with idempotency
        with self.db_manager.session() as session:
            repo = ApprovalRepository(session)
            existing = repo.get_approval(context, target_type, target_id, payload_hash)
            if existing:
                return ApprovalRecord(
                    approval_id=existing.id,
                    organization_id=existing.organization_id,
                    project_id=existing.project_id,
                    target_type=existing.target_type,
                    target_id=existing.target_id,
                    payload_hash=existing.payload_hash,
                    approved_by=existing.approved_by,
                    status=ApprovalStatus(existing.status),
                    comments=existing.comments,
                    created_at=existing.created_at.isoformat(),
                )

            approval_id = f"appr_{uuid.uuid4().hex[:16]}"
            model = repo.record_approval(
                context=context,
                approval_id=approval_id,
                target_type=target_type,
                target_id=target_id,
                payload_hash=payload_hash,
                approved_by=context.actor.actor_id,
                status="approved",
                comments=comments,
            )

            record = ApprovalRecord(
                approval_id=model.id,
                organization_id=model.organization_id,
                project_id=model.project_id,
                target_type=model.target_type,
                target_id=model.target_id,
                payload_hash=model.payload_hash,
                approved_by=model.approved_by,
                status=ApprovalStatus.APPROVED,
                comments=model.comments,
                created_at=model.created_at.isoformat(),
            )

        # 4. Audit trail
        self.audit_logger.record(
            event_type="core.approval.granted",
            context=context,
            resource_id=target_id,
            status=AuditStatus.ALLOWED,
            payload={
                "target_type": target_type,
                "payload_hash": payload_hash,
                "approved_by": context.actor.actor_id,
            },
        )

        return record

    def verify_approval(
        self,
        context: SecurityContext,
        target_type: str,
        target_id: str,
        expected_payload_hash: str,
    ) -> ApprovalRecord:
        """Verifies that an approved record exists matching the target and exact payload hash."""
        with self.db_manager.session() as session:
            repo = ApprovalRepository(session)
            approval = repo.get_approval(context, target_type, target_id, expected_payload_hash)
            if not approval:
                # Check if approval exists for this target with a DIFFERENT payload hash
                any_approval = (
                    session.query(repo.session.query(ApprovalRepository).class_ if False else None)  # simple query
                )
                from database.schema import ApprovalModel
                diff_approval = (
                    session.query(ApprovalModel)
                    .filter_by(
                        organization_id=context.organization_id,
                        project_id=context.project_id,
                        target_type=target_type,
                        target_id=target_id,
                        status="approved",
                    )
                    .first()
                )
                if diff_approval:
                    raise PayloadHashMismatchError(
                        f"Target '{target_id}' was approved with payload hash '{diff_approval.payload_hash}', "
                        f"but current configuration produces '{expected_payload_hash}'. Modification after approval is forbidden."
                    )

                raise ApprovalRequiredError(
                    f"No approval record found for {target_type} '{target_id}' with hash '{expected_payload_hash}'."
                )

            return ApprovalRecord(
                approval_id=approval.id,
                organization_id=approval.organization_id,
                project_id=approval.project_id,
                target_type=approval.target_type,
                target_id=approval.target_id,
                payload_hash=approval.payload_hash,
                approved_by=approval.approved_by,
                status=ApprovalStatus(approval.status),
                comments=approval.comments,
                created_at=approval.created_at.isoformat(),
            )
