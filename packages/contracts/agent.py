"""Domain contracts for Agent Factory.

Defines schemas for AgentBlueprint, AgentVersion, and AgentAssignment.
Enforces immutable versioning, canonical payload hash computation, and tenant scoping.
Complies with ARYN-ARCH-001 Section 04 and AGENTS.md rules 3, 4, 7.
"""

from __future__ import annotations

import datetime
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VersionIntegrityError(ValueError):
    """Stored configuration does not match its canonical hash."""


class AgentVersionStatus(str, Enum):
    DRAFT = "draft"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class AgentBlueprint(BaseModel):
    """The root specification for an agent persona."""
    id: str
    organization_id: str
    project_id: str
    name: str
    slug: str
    description: Optional[str] = None
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class AgentVersion(BaseModel):
    """An immutable, versioned configuration of an agent."""
    id: str
    blueprint_id: str
    version_number: str
    status: AgentVersionStatus = AgentVersionStatus.DRAFT
    system_prompt: str
    model: str
    tool_grants: List[str] = Field(default_factory=list)
    temperature: float = Field(default=0.7, ge=0, le=2, allow_inf_nan=False)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    evaluation_id: Optional[str] = None
    published_at: Optional[str] = None
    published_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def canonical_payload(self) -> str:
        """Versioned JSON; exact parameters and all security metadata are covered."""
        canonical = {
            "canonical_format": 2,
            "id": self.id,
            "blueprint_id": self.blueprint_id,
            "version_number": self.version_number,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "tool_grants": sorted(self.tool_grants),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "metadata": self.metadata,
        }
        return json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def calculate_payload_hash(self) -> str:
        encoded = self.canonical_payload().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def verify_integrity(self) -> None:
        if not self.payload_hash or self.payload_hash != self.calculate_payload_hash():
            raise VersionIntegrityError("Agent version integrity check failed; create and evaluate a new version.")

    @classmethod
    def from_stored(cls, row) -> AgentVersion:
        try:
            version = cls(
                id=row.id, blueprint_id=row.blueprint_id, version_number=row.version_number,
                status=row.status, system_prompt=row.system_prompt, model=row.model,
                tool_grants=json.loads(row.tool_grants_json), temperature=row.temperature,
                max_tokens=row.max_tokens, metadata=json.loads(row.metadata_json),
                payload_hash=row.payload_hash, evaluation_id=row.evaluation_id,
                published_at=row.published_at.isoformat() if row.published_at else None,
                published_by=row.published_by, created_at=row.created_at.isoformat(),
            )
            version.verify_integrity()
            return version
        except (ValueError, TypeError) as exc:
            raise VersionIntegrityError("Stored agent version integrity check failed.") from exc


class AgentAssignment(BaseModel):
    """Binds a published AgentVersion to an operational scope (project and optional division)."""
    id: str
    organization_id: str
    project_id: str
    division_id: Optional[str] = None
    blueprint_id: str
    version_id: str
    role_name: str
    status: str = "active"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
