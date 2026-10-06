"""Model and provider contracts for ARYN infrastructure.

Defines provider routing, model specifications, and capability contracts.
Complies with ARYN-TECH-001 ADR-005 (No vendor lock-in, no silent fallback).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


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

    def validate_request(self, requested_model: str) -> None:
        """Enforces that the requested model is registered and permitted."""
        if requested_model not in self.allowed_models:
            raise ValueError(
                f"Model '{requested_model}' is not permitted by ARYN routing policy. "
                f"Allowed models: {self.allowed_models}. Silent fallback is forbidden."
            )
