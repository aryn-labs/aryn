"""Core domain contracts for ARYN infrastructure.

Defines identity, security context, policy decisions, audit envelopes, and budget rules.
Complies with ARYN-ARCH-001 and ARYN-SEC-001.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Actor(BaseModel):
    actor_id: str
    actor_type: ActorType = ActorType.USER
    roles: List[str] = Field(default_factory=lambda: ["operator"])
    organization_id: str
    project_id: Optional[str] = None


class SecurityContext(BaseModel):
    actor: Actor
    organization_id: str
    project_id: str
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: Optional[str] = None
    identity_token: Optional[str] = None

    def validate_ownership(self, target_org_id: str, target_project_id: Optional[str] = None) -> bool:
        """Enforces tenant and project boundary isolation."""
        if self.organization_id != target_org_id:
            return False
        if target_project_id and self.project_id != target_project_id:
            return False
        return True


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str
    matched_rules: List[str] = Field(default_factory=list)
    enforced_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class BudgetRule(BaseModel):
    max_tokens_per_run: int = 4096
    max_turns: int = 10
    max_cost_usd: float = 0.50


class AuditStatus(str, Enum):
    ATTEMPTED = "attempted"
    ALLOWED = "allowed"
    DENIED = "denied"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditEvent(BaseModel):
    """Event envelope matching ARYN-ARCH-001 Section 07."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    schema_version: str = "1.0.0"
    occurred_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    organization_id: str
    project_id: str
    actor_type: str
    actor_id: str
    correlation_id: str
    resource_id: str
    causation_id: Optional[str] = None
    status: AuditStatus
    redacted_payload: Dict[str, Any] = Field(default_factory=dict)
    integrity_reference: str = ""
    attestation: str = ""

    def authenticated_payload(self) -> dict:
        from packages.contracts.timestamps import canonical_timestamp
        return {"event_id": self.event_id, "event_type": self.event_type, "schema_version": self.schema_version,
            "occurred_at": canonical_timestamp(self.occurred_at), "organization_id": self.organization_id,
            "project_id": self.project_id, "actor_type": self.actor_type, "actor_id": self.actor_id,
            "correlation_id": self.correlation_id, "resource_id": self.resource_id,
            "causation_id": self.causation_id, "status": self.status.value, "payload": self.redacted_payload}

    def calculate_integrity(self) -> str:
        """Calculates a deterministic SHA256 integrity hash over canonical event fields."""
        canonical = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "resource_id": self.resource_id,
            "status": self.status.value if isinstance(self.status, AuditStatus) else str(self.status),
            "payload": self.redacted_payload,
        }
        if self.schema_version != "1.0.0":
            canonical = self.authenticated_payload()
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
