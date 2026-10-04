"""ARYN Core Audit Logger.

Generates immutable audit event envelopes with strict, automatic secret redaction.
Supports in-memory tracking and persistent database repository storage.
Complies with ARYN-ARCH-001 Section 07 and ARYN-SEC-001.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from packages.contracts.core import AuditEvent, AuditStatus, SecurityContext


class AuditLogger:
    """Authoritative audit logger for ARYN operations."""

    SENSITIVE_KEY_PATTERNS = re.compile(
        r"(api[_-]?key|secret|token|password|auth|authorization|credential|bearer)",
        re.IGNORECASE,
    )
    BEARER_PATTERN = re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE)

    def __init__(self, db_manager: Optional[Any] = None) -> None:
        self.db_manager = db_manager
        self._events: List[AuditEvent] = []

    def redact_secrets(self, data: Any) -> Any:
        """Recursively scrubs secret keys and sensitive credential patterns."""
        if isinstance(data, dict):
            redacted = {}
            for k, v in data.items():
                if self.SENSITIVE_KEY_PATTERNS.search(str(k)):
                    redacted[k] = "[REDACTED]"
                else:
                    redacted[k] = self.redact_secrets(v)
            return redacted
        elif isinstance(data, list):
            return [self.redact_secrets(item) for item in data]
        elif isinstance(data, str):
            # Scrub explicit Bearer tokens
            scrubbed = self.BEARER_PATTERN.sub("Bearer [REDACTED]", data)
            return scrubbed
        return data

    def record(
        self,
        event_type: str,
        context: SecurityContext,
        resource_id: str,
        status: AuditStatus,
        payload: Optional[Dict[str, Any]] = None,
        causation_id: Optional[str] = None,
    ) -> AuditEvent:
        """Creates, redacts, signs, and records an audit event envelope."""
        clean_payload = self.redact_secrets(payload or {})

        event = AuditEvent(
            event_type=event_type,
            organization_id=context.organization_id,
            project_id=context.project_id,
            actor_type=context.actor.actor_type.value,
            actor_id=context.actor.actor_id,
            correlation_id=context.correlation_id,
            resource_id=resource_id,
            causation_id=causation_id or context.causation_id,
            status=status,
            redacted_payload=clean_payload,
        )
        event.integrity_reference = event.calculate_integrity()
        self._events.append(event)

        # Persist to database if db_manager is configured
        if self.db_manager:
            from database.repositories.audit_repo import AuditRepository
            with self.db_manager.session() as session:
                repo = AuditRepository(session)
                repo.record_event(event)

        return event

    def get_events_for_correlation(self, correlation_id: str, context: Optional[SecurityContext] = None) -> List[AuditEvent]:
        if self.db_manager and context:
            from database.repositories.audit_repo import AuditRepository
            with self.db_manager.session() as session:
                repo = AuditRepository(session)
                db_models = repo.list_by_correlation(context, correlation_id)
                if db_models:
                    return [
                        AuditEvent(
                            event_id=m.event_id,
                            event_type=m.event_type,
                            schema_version=m.schema_version,
                            occurred_at=m.occurred_at,
                            organization_id=m.organization_id,
                            project_id=m.project_id,
                            actor_type=m.actor_type,
                            actor_id=m.actor_id,
                            correlation_id=m.correlation_id,
                            resource_id=m.resource_id,
                            causation_id=m.causation_id,
                            status=AuditStatus(m.status),
                            redacted_payload=json.loads(m.redacted_payload_json),
                            integrity_reference=m.integrity_reference,
                        )
                        for m in db_models
                    ]

        return [e for e in self._events if e.correlation_id == correlation_id]

    def all_events(self) -> List[AuditEvent]:
        return list(self._events)
