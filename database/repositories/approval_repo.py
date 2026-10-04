"""Repository for cryptographic approvals bound to exact payload hashes."""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import ApprovalModel, utc_now
from packages.contracts.core import SecurityContext
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    TenantIsolationError,
)


class ApprovalRepository:
    """Stores and retrieves human authorizations tied to exact payload hashes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_approval(
        self,
        context: SecurityContext,
        approval_id: str,
        target_type: str,
        target_id: str,
        payload_hash: str,
        approved_by: str,
        status: str = "approved",
        comments: Optional[str] = None,
    ) -> ApprovalModel:
        approval = ApprovalModel(
            id=approval_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            target_type=target_type,
            target_id=target_id,
            payload_hash=payload_hash,
            approved_by=approved_by,
            status=status,
            comments=comments,
            created_at=utc_now(),
        )
        self.session.add(approval)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Approval with id '{approval_id}' already exists."
            ) from exc
        return approval

    def get_approval(
        self,
        context: SecurityContext,
        target_type: str,
        target_id: str,
        payload_hash: str,
    ) -> Optional[ApprovalModel]:
        """Looks up an active approval record matching exact target and payload hash."""
        return (
            self.session.query(ApprovalModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
                target_type=target_type,
                target_id=target_id,
                payload_hash=payload_hash,
                status="approved",
            )
            .first()
        )
