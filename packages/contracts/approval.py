"""Domain contracts for cryptographic approval integration.

Defines schemas for ApprovalRecord and ApprovalStatus.
Complies with ARYN-ARCH-001 Section 05 and AGENTS.md rules 4, 7.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRecord(BaseModel):
    """Cryptographic approval binding human authorization to an exact payload hash."""
    approval_id: str
    organization_id: str
    project_id: str
    target_type: str  # e.g. "agent_version"
    target_id: str
    payload_hash: str
    approved_by: str  # Human user ID
    status: ApprovalStatus = ApprovalStatus.APPROVED
    comments: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
