"""Model and provider contracts for ARYN infrastructure.

Defines provider routing, model specifications, and capability contracts.
Complies with ARYN-TECH-001 ADR-005 (No vendor lock-in, no silent fallback).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


TOOL_PROBE_PROMPT = "Read aryn-core using aryn_fixture_lookup and return its text as JSON summary."
TOOL_PROBE_SYSTEM = "Call aryn_fixture_lookup exactly once with key aryn-core. Use the verified tool result. Return only JSON with summary equal to its text."


def tool_probe_request(model, idempotency_key):
    from packages.contracts.runtime import RunRequest
    return RunRequest(model=model, prompt=TOOL_PROBE_PROMPT, system_instructions=TOOL_PROBE_SYSTEM,
        max_tokens=128, max_total_tokens=4096, timeout_seconds=60, temperature=0,
        max_iterations=2, max_tool_calls=1, idempotency_key=idempotency_key)


def tool_probe_output_contract():
    from packages.contracts.bench import OutputContract
    return OutputContract(format="json", strict=True, schema_definition={"type": "object",
        "properties": {"summary": {"const": "ARYN Core owns execution authorization."}}, "required": ["summary"]})


class ModelProbeBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    origin: Literal["gateway_response", "isolated_test_double", "unavailable"] = "unavailable"
    runtime_configuration: str = Field(pattern=r"^[a-f0-9]{64}$")
    gateway_configuration: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_configuration: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ModelProbeEvidence(BaseModel):
    """Core-signed, short-lived observation; never an authorization grant."""
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    mode: Literal["tool_calling"] = "tool_calling"
    run_id: str = Field(pattern=r"^run_[a-f0-9]{32}$")
    model: str = Field(max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$")
    provider: Optional[str] = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$")
    reported_model: Optional[str] = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$")
    binding: Optional[ModelProbeBinding] = None
    observed_at: float
    expires_at: float
    tool_call_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    iterations: Literal[2] = 2
    tool_calls: Literal[1] = 1
    transcript_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def live_eligible(self):
        return bool(self.provider and self.provider.lower() not in {"9router", "hermes", "unknown", "unavailable", "custom", "mock", "isolated_test_double", "test-double"}
            and self.reported_model == self.model and self.binding
            and self.binding.origin == "gateway_response" and self.binding.provider_configuration)


class ModelCapabilities(BaseModel):
    """Evidence about one exact model; catalog membership grants no capability."""
    model_config = ConfigDict(extra="forbid")
    model: str
    text_generation: Literal["supported", "unsupported", "unknown"] = "unknown"
    structured_output: Literal["supported", "unsupported", "unknown"] = "unknown"
    tool_calling: Literal["supported", "unsupported", "unknown"] = "unknown"
    source: str = "capability_evidence_unavailable"


class ModelProviderType(str, Enum):
    NINE_ROUTER = "9router"
    GEMINI = "gemini"
    NOUS = "nous"
    BYOK = "byok"
    LOCAL = "local"
    MOCK = "mock"


class ModelSpec(BaseModel):
    provider: ModelProviderType
    model_id: str
    display_name: str
    context_window: int = 128000
    supports_tools: bool = False
    requires_api_key: bool = True
    endpoint_override: Optional[str] = None
    rate_limits: Dict[str, int] = Field(default_factory=lambda: {"rpm": 60, "tpm": 100000})


class ModelRoutingConfig(BaseModel):
    """Routing configuration with strict safety invariants."""
    active_provider: ModelProviderType = ModelProviderType.NINE_ROUTER
    active_model: Optional[str] = None
    allowed_models: List[str]
    # Invariant per ADR-005: Never fallback silently between providers or models.
    allow_fallback: bool = False
    fallback_provider: Optional[ModelProviderType] = None
    fallback_model: Optional[str] = None
