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
    temperature: float = 0.7
    max_tokens: int = 2048
    metadata: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    evaluation_id: Optional[str] = None
    published_at: Optional[str] = None
    published_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def calculate_payload_hash(self) -> str:
        """Computes a deterministic SHA-256 hash of immutable version properties."""
        canonical = {
            "blueprint_id": self.blueprint_id,
            "version_number": self.version_number,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "tool_grants": sorted(self.tool_grants),
            "temperature": round(self.temperature, 4),
            "max_tokens": self.max_tokens,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


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
