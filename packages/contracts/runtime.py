"""Runtime adapter contract definitions for ARYN infrastructure.

Defines the interface between ARYN Core and external/isolated runtime engines (such as Hermes).
Complies with ARYN-TECH-001 ADR-004 and ARYN-SEC-001.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.core import SecurityContext
from packages.contracts.model import ModelProbeBinding


class RunStatus(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    STOPPING = "stopping"
    OUTCOME_UNKNOWN = "outcome_unknown"


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
    supports_governed_tool_turns: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    call_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    arguments: Dict[str, Any]


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str
    organization_id: str
    project_id: str
    deadline_at: float = Field(allow_inf_nan=False)
    call_number: int = Field(ge=1, le=2, strict=True)


class ToolTurnRequest(BaseModel):
    """Private Core-to-runtime turn. Runtime proposes and never executes tools."""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    run_id: str = Field(min_length=1, max_length=64)
    organization_id: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)
    iteration: int = Field(ge=1, le=3, strict=True)
    request: RunRequest
    tool_names: List[str] = Field(max_length=1)
    history: List[Dict[str, Any]] = Field(default_factory=list, max_length=8)
    verification_mode: Optional[Literal["tool_calling"]] = None

    @model_validator(mode="after")
    def bounded_probe(self):
        if self.verification_mode is None:
            return self
        from packages.contracts.model import TOOL_PROBE_PROMPT, TOOL_PROBE_SYSTEM
        from packages.contracts.bench import strict_json_loads
        from packages.tool_adapters.fixture import NAME, FixtureInput, FixtureOutput
        r = self.request
        valid = (self.tool_names == [NAME] and self.iteration <= 2 and r.max_iterations == 2
            and r.max_tool_calls == 1 and r.max_tokens <= 128 and r.timeout_seconds <= 60
            and r.temperature == 0 and r.system_instructions == TOOL_PROBE_SYSTEM and not r.session_id
            and r.metadata == {"initial_prompt": TOOL_PROBE_PROMPT}
            and r.max_total_tokens is not None and r.max_total_tokens <= 4096)
        if self.iteration == 1:
            valid = valid and not self.history and r.prompt == TOOL_PROBE_PROMPT
        else:
            valid = valid and r.prompt == "Continue using the verified tool result." and len(self.history) == 3
            if valid:
                user, assistant, result = self.history
                calls = assistant.get("tool_calls", [])
                valid = (user == {"role": "user", "content": TOOL_PROBE_PROMPT}
                    and set(assistant) == {"role", "content", "tool_calls"}
                    and assistant.get("role") == "assistant" and assistant.get("content") == ""
                    and isinstance(calls, list) and len(calls) == 1)
                if valid:
                    call = calls[0]
                    try:
                        arguments = FixtureInput.model_validate(strict_json_loads(call["function"]["arguments"]))
                        ToolCall(call_id=call["id"], name=call["function"]["name"], arguments=arguments.model_dump())
                        valid = (set(call) == {"id", "type", "function"} and set(call["function"]) == {"name", "arguments"}
                            and call["type"] == "function" and call["function"]["name"] == NAME
                            and arguments.key == "aryn-core" and result == {"role": "tool", "name": NAME,
                                "tool_call_id": call["id"], "content": result.get("content")}
                            and FixtureOutput.model_validate(strict_json_loads(result["content"])).model_dump()
                                == {"key": "aryn-core", "text": "ARYN Core owns execution authorization."})
                    except (ValueError, KeyError, TypeError):
                        valid = False
        if not valid:
            raise ValueError("Only the fixed synthetic capability probe is allowed.")
        return self


class ToolTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    run_id: str
    iteration: int = Field(ge=1, le=3, strict=True)
    result: RunResult
    tool_calls: List[ToolCall] = Field(default_factory=list, max_length=2)


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


class ProviderRequestError(RuntimeError):
    """Sanitized observation, not proof of billing state or a safe retry grant."""
    def __init__(self, code: Literal["provider_rate_limited", "provider_insufficient_credit", "provider_quota_exhausted", "provider_unavailable"]):
        if code not in {"provider_rate_limited", "provider_insufficient_credit", "provider_quota_exhausted", "provider_unavailable"}:
            raise ValueError("Unknown provider error code")
        self.code = code
        super().__init__(code)


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
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600, allow_inf_nan=False)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    max_cost_usd: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    max_total_tokens: Optional[int] = Field(default=None, ge=1)
    max_input_tokens: Optional[int] = Field(default=None, ge=1)
    max_iterations: int = Field(default=1, ge=1, le=3, strict=True)
    max_tool_calls: int = Field(default=0, ge=0, le=2, strict=True)


class RunUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0, strict=True)
    output_tokens: int = Field(default=0, ge=0, strict=True)
    total_tokens: int = Field(default=0, ge=0, strict=True)
    availability: Literal["measured", "unavailable"] = "unavailable"
    cost_usd: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    cost_source: Optional[Literal["provider_usage", "runtime_meter"]] = None

    @model_validator(mode="before")
    @classmethod
    def explicit_usage(cls, value):
        if isinstance(value, dict) and "availability" not in value and all(k in value for k in ("input_tokens", "output_tokens", "total_tokens")):
            value = {**value, "availability": "measured"}
        return value


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
    execution_evidence: Optional[Dict[str, Any]] = None
    assignment_id: Optional[str] = None
    agent_version_id: Optional[str] = None
    agent_payload_hash: Optional[str] = None
    assignment_transition_id: Optional[str] = None
    requested_model: Optional[str] = None
    actual_model: Optional[str] = None
    reported_model: Optional[str] = None
    model_evidence: Optional[ModelProbeBinding] = None
    gateway: Optional[Literal["9Router"]] = None
    runtime_backend: Optional[Literal["Hermes"]] = None
    provider: Optional[str] = None
    execution_claim_verified: bool = False
    assignment_provenance_verified: bool = False
    runtime_run_id: Optional[str] = None
    execution_provenance: Optional[Dict[str, Any]] = None
    effective_limits: Dict[str, Any] = Field(default_factory=dict)
    output_reference: Optional[str] = None
    error_code: Optional[str] = None


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

    async def model_capabilities(self, model: str):
        from packages.contracts.model import ModelCapabilities
        return ModelCapabilities(model=model)

    async def execute_tool_turn(self, request: ToolTurnRequest, context: SecurityContext) -> ToolTurnResult:
        raise RuntimeGatewayError()

    async def require_model_candidate(self, model: str):
        # Only adapters with an explicit exact-route candidate contract may relax readiness.
        await self.require_model_available(model)

    async def capability_verification_binding(self):
        """Unregistered/test runtimes cannot issue live capability attestations."""
        return None

    async def record_tool_verification(self, evidence, attestation, verifier):
        return False

    def invalidate_tool_verification(self, model):
        return None

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
