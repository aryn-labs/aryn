"""ARYN Core Audit Logger.

Generates immutable audit event envelopes with strict, automatic secret redaction.
Complies with ARYN-ARCH-001 Section 07 and ARYN-SEC-001.
"""

from __future__ import annotations

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

    def __init__(self) -> None:
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
        return event

    def get_events_for_correlation(self, correlation_id: str) -> List[AuditEvent]:
        return [e for e in self._events if e.correlation_id == correlation_id]

    def all_events(self) -> List[AuditEvent]:
        return list(self._events)
