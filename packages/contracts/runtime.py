"""Runtime adapter contract definitions for ARYN infrastructure.

Defines the interface between ARYN Core and external/isolated runtime engines (such as Hermes).
Complies with ARYN-TECH-001 ADR-004 and ARYN-SEC-001.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
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


class RuntimeModelAvailability(BaseModel):
    model: str
    status: Literal["available", "unavailable", "unknown"] = "unknown"
    source: str = "unsupported_discovery"
    reason: str = "availability_unknown"


class GatewayDiscovery(BaseModel):
    gateway: Literal["9Router"] = "9Router"
    connected: bool = False
    discovery_valid: bool = False
    reason: str = "discovery_unavailable"
    models: List[Dict[str, Any]] = Field(default_factory=list)


class GatewayUnavailableError(RuntimeError):
    def __init__(self):
        super().__init__("Model Gateway tidak dapat dijangkau atau discovery belum valid.")


class ModelIdentityError(RuntimeError):
    def __init__(self):
        super().__init__("Model aktual berbeda dengan model yang disetujui. Eksekusi ditolak.")


class RuntimeGatewayError(RuntimeError):
    def __init__(self):
        super().__init__("ARYN Runtime belum siap. Routing Model Gateway dan bukti model aktual belum dapat diverifikasi.")


class ModelUnavailableError(RuntimeError):
    """No verified runtime availability; never retry with a different model."""

    def __init__(self, availability):
        self.model = availability.model
        self.availability = availability.status
        self.reason = availability.reason
        message = (
            "Model tidak tersedia melalui Model Gateway. Pilih model lain sebelum menjalankan Bench atau eksekusi."
            if availability.status == "unavailable" else
            "Ketersediaan model belum dapat diverifikasi. Bench dan eksekusi diblokir sampai tersedia bukti ketersediaan yang valid."
        )
        super().__init__(message)


class RunRequest(BaseModel):
    prompt: str
    system_instructions: Optional[str] = None
    model: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=255)
    timeout_seconds: float = 30.0
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
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
    requested_model: Optional[str] = None
    actual_model: Optional[str] = None
    gateway: Optional[Literal["9Router"]] = None
    runtime_backend: Optional[Literal["Hermes"]] = None
    provider: Optional[str] = None


class RuntimeTrace(BaseModel):
    run_id: str
    events: List[Dict[str, Any]] = Field(default_factory=list)
    raw_trace: Optional[Dict[str, Any]] = None
    available: bool = False
    unavailability_reason: Optional[str] = None


class RuntimeAdapter(ABC):
    """Abstract interface that every ARYN runtime adapter must implement."""

    async def discover_models(self, *, refresh: bool = False) -> GatewayDiscovery:
        return GatewayDiscovery()

    async def gateway_binding(self) -> bool:
        return False

    async def model_availability(self, model: str, *, refresh: bool = False) -> RuntimeModelAvailability:
        """Unsupported discovery is unknown, never proof of model readiness."""
        return RuntimeModelAvailability(model=model)

    async def require_model_available(self, model: str) -> None:
        availability = await self.model_availability(model, refresh=True)
        if availability.model != model:
            raise ModelUnavailableError(RuntimeModelAvailability(model=model, reason="discovery_model_mismatch"))
        if availability.status != "available":
            raise ModelUnavailableError(availability)

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
        """Request interruption; acknowledgment is not proof of terminal cancellation."""
        pass

    @abstractmethod
    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        """Retrieve execution events and traces for a run."""
        pass
