"""Runtime adapter contract definitions for ARYN infrastructure.

Defines the interface between ARYN Core and external/isolated runtime engines (such as Hermes).
Complies with ARYN-TECH-001 ADR-004 and ARYN-SEC-001.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from packages.contracts.core import SecurityContext


class RunStatus(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    STOPPING = "stopping"


class RuntimeHealth(BaseModel):
    is_healthy: bool
    status: str
    platform: str
    version: str
    listener_url: str
    details: Dict[str, Any] = Field(default_factory=dict)


class RuntimeCapabilities(BaseModel):
    enabled_toolsets: List[str]
    available_toolsets: List[str]
    tools_confined: bool  # True when risky tools (terminal, file, code_exec, browser) are disabled
    supports_cancellation: bool = True
    supports_streaming: bool = True
    details: Dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    prompt: str
    system_instructions: Optional[str] = None
    model: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    timeout_seconds: float = 30.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    output: str
    usage: RunUsage = Field(default_factory=RunUsage)
    model: str
    created_at: float
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    raw_response: Dict[str, Any] = Field(default_factory=dict)


class RuntimeTrace(BaseModel):
    run_id: str
    events: List[Dict[str, Any]] = Field(default_factory=list)
    raw_trace: Optional[Dict[str, Any]] = None


class RuntimeAdapter(ABC):
    """Abstract interface that every ARYN runtime adapter must implement."""

    @abstractmethod
    async def health(self) -> RuntimeHealth:
        """Check runtime health and connectivity."""
        pass

    @abstractmethod
    async def capabilities(self) -> RuntimeCapabilities:
        """Inspect runtime capabilities and verify tool confinement."""
        pass

    @abstractmethod
    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        """Initiate an asynchronous agent run and return the assigned run_id."""
        pass

    @abstractmethod
    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        """Retrieve the current state or final output of an agent run."""
        pass

    @abstractmethod
    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        """Request immediate cancellation/interruption of a running agent."""
        pass

    @abstractmethod
    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        """Retrieve execution events and traces for a run."""
        pass
