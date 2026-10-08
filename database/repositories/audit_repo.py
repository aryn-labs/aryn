"""Repository for persistent immutable audit events.

Complies with ARYN-ARCH-001 Section 07 and ARYN-SEC-001.
"""

from __future__ import annotations

import datetime
import json
from typing import List
from sqlalchemy.orm import Session, object_session
from sqlalchemy.exc import IntegrityError

from database.schema import AuditEventModel
from packages.contracts.core import AuditEvent, SecurityContext
from packages.contracts.timestamps import canonical_timestamp
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

        occurred_dt = datetime.datetime.fromisoformat(canonical_timestamp(event.occurred_at))
        if event.schema_version != "1.0.0":
            manager = self.session.info.get("db_manager")
            if (event.schema_version != "2.0.0" or manager is None
                    or not manager.evidence_signer.verify("audit_event", event.authenticated_payload(), event.attestation)
                    or event.integrity_reference != event.calculate_integrity()):
                raise ValueError("Authenticated audit envelope is invalid.")

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
            attestation=event.attestation,
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
    def verify_event_integrity(event_model: AuditEventModel, signer=None) -> bool:
        """Verifies that an audit event stored in DB has not been tampered with."""
        import hashlib
        try:
            payload = json.loads(event_model.redacted_payload_json)
            if event_model.id != event_model.event_id:
                return False
            if event_model.attestation or event_model.schema_version != "1.0.0":
                session = object_session(event_model)
                manager = session.info.get("db_manager") if session else None
                signer = signer or (manager.evidence_signer if manager else None)
                event = AuditRepository.contract(event_model)
                return bool(signer and event.schema_version == "2.0.0"
                    and event.calculate_integrity() == event_model.integrity_reference
                    and signer.verify("audit_event", event.authenticated_payload(), event_model.attestation))
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

    @staticmethod
    def contract(row):
        return AuditEvent(event_id=row.event_id, event_type=row.event_type, schema_version=row.schema_version,
            occurred_at=canonical_timestamp(row.occurred_at, stored=True), organization_id=row.organization_id,
            project_id=row.project_id, actor_type=row.actor_type, actor_id=row.actor_id,
            correlation_id=row.correlation_id, resource_id=row.resource_id, causation_id=row.causation_id,
            status=row.status, redacted_payload=json.loads(row.redacted_payload_json),
            integrity_reference=row.integrity_reference, attestation=row.attestation or "")

    def verify_authenticated_event(self, row):
        """Legacy checksums are readable compatibility data, never authority."""
        return bool(row.attestation and self.verify_event_integrity(row))
