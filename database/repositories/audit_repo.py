"""Repository for persistent immutable audit events.

Complies with ARYN-ARCH-001 Section 07 and ARYN-SEC-001.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import AuditEventModel, utc_now
from packages.contracts.core import AuditEvent, SecurityContext
from database.repositories.exceptions import DuplicateEntityError, EntityNotFoundError, TenantIsolationError


class AuditRepository:
    """Stores and retrieves immutable audit event envelopes with integrity hashes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_event(self, event: AuditEvent) -> AuditEventModel:
        """Persists an AuditEvent contract instance into the database."""
        existing = self.session.query(AuditEventModel).filter_by(event_id=event.event_id).first()
        if existing:
            raise DuplicateEntityError(f"Audit event with id '{event.event_id}' already exists.")

        payload_str = json.dumps(event.redacted_payload, sort_keys=True)

        occurred_dt: datetime.datetime
        if isinstance(event.occurred_at, str):
            try:
                occurred_dt = datetime.datetime.fromisoformat(event.occurred_at)
            except Exception:
                occurred_dt = utc_now()
        elif isinstance(event.occurred_at, datetime.datetime):
            occurred_dt = event.occurred_at
        else:
            occurred_dt = utc_now()

        model = AuditEventModel(
            id=event.event_id,
            event_id=event.event_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            occurred_at=occurred_dt,
            organization_id=event.organization_id,
            project_id=event.project_id,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            correlation_id=event.correlation_id,
            resource_id=event.resource_id,
            causation_id=event.causation_id,
            status=event.status.value if hasattr(event.status, "value") else str(event.status),
            redacted_payload_json=payload_str,
            integrity_reference=event.integrity_reference or event.calculate_integrity(),
        )
        self.session.add(model)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(f"Audit event with id '{event.event_id}' already exists.") from exc
        return model

    def get_event(self, context: SecurityContext, event_id: str) -> AuditEventModel:
        """Retrieves an audit event enforcing tenant isolation."""
        event = self.session.query(AuditEventModel).filter_by(event_id=event_id).first()
        if not event:
            raise EntityNotFoundError(f"Audit event '{event_id}' not found.")
        if event.organization_id != context.organization_id or event.project_id != context.project_id:
            raise TenantIsolationError(
                f"Tenant boundary violation: Audit event belongs to org '{event.organization_id}', "
                f"not context org '{context.organization_id}'."
            )
        return event

    def list_by_correlation(self, context: SecurityContext, correlation_id: str) -> List[AuditEventModel]:
        """Lists audit events for a correlation ID within the authorized tenant."""
        return (
            self.session.query(AuditEventModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
                correlation_id=correlation_id,
            )
            .order_by(AuditEventModel.occurred_at.asc())
            .all()
        )

    def list_by_project(self, context: SecurityContext, limit: int = 100) -> List[AuditEventModel]:
        """Lists audit events for the context's project."""
        return (
            self.session.query(AuditEventModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
            )
            .order_by(AuditEventModel.occurred_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def verify_event_integrity(event_model: AuditEventModel) -> bool:
        """Verifies that an audit event stored in DB has not been tampered with."""
        import hashlib
        try:
            payload = json.loads(event_model.redacted_payload_json)
        except Exception:
            return False

        occurred_str = (
            event_model.occurred_at.isoformat()
            if hasattr(event_model.occurred_at, "isoformat")
            else str(event_model.occurred_at)
        )
        canonical = {
            "event_id": event_model.event_id,
            "event_type": event_model.event_type,
            "occurred_at": occurred_str,
            "organization_id": event_model.organization_id,
            "project_id": event_model.project_id,
            "actor_id": event_model.actor_id,
            "correlation_id": event_model.correlation_id,
            "resource_id": event_model.resource_id,
            "status": event_model.status,
            "payload": payload,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        computed = hashlib.sha256(encoded).hexdigest()
        return computed == event_model.integrity_reference
