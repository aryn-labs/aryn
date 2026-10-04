"""Explicit model router for ARYN infrastructure.

Enforces ADR-005: Explicit routing, prevent vendor lock-in, and strictly forbid silent fallbacks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from packages.contracts.model import ModelProviderType, ModelRoutingConfig, ModelSpec
from .providers.gemini import GeminiModelAdapter
from .providers.nous import NousModelAdapter
from .providers.mock import MockModelAdapter


class ModelRoutingError(Exception):
    """Raised when model routing fails or policy is violated."""
    pass


class ModelRouter:
    """Manages model providers and routes requests explicitly."""

    def __init__(
        self,
        config: Optional[ModelRoutingConfig] = None,
        gemini_api_key: Optional[str] = None,
        nous_api_key: Optional[str] = None,
    ) -> None:
        self.gemini_adapter = GeminiModelAdapter(api_key=gemini_api_key)
        self.nous_adapter = NousModelAdapter(api_key=nous_api_key)
        self.mock_adapter = MockModelAdapter()

        # Build catalog of all registered models
        self.catalog: Dict[str, ModelSpec] = {}
        for spec in self.gemini_adapter.SUPPORTED_MODELS.values():
            self.catalog[spec.model_id] = spec
        for spec in self.nous_adapter.SUPPORTED_MODELS.values():
            self.catalog[spec.model_id] = spec
        for spec in self.mock_adapter.SUPPORTED_MODELS.values():
            self.catalog[spec.model_id] = spec

        self.config = config or ModelRoutingConfig(
            active_provider=ModelProviderType.NOUS,
            active_model="stealth/space-bunny-alpha",
            allowed_models=list(self.catalog.keys()),
            allow_fallback=False,
        )

    def resolve_model(self, requested_model: Optional[str] = None) -> ModelSpec:
        """Resolves a model spec strictly against policy. Forbids silent fallback."""
        model_id = requested_model or self.config.active_model

        if model_id not in self.config.allowed_models:
            raise ModelRoutingError(
                f"Model '{model_id}' is not in the allowed routing list: {self.config.allowed_models}. "
                "Silent fallback is forbidden by ARYN ADR-005."
            )

        if model_id not in self.catalog:
            raise ModelRoutingError(
                f"Model '{model_id}' is not registered with any configured provider adapter."
            )

        spec = self.catalog[model_id]
        return spec

    def get_adapter_for_spec(self, spec: ModelSpec) -> Any:
        if spec.provider == ModelProviderType.GEMINI:
            return self.gemini_adapter
        elif spec.provider == ModelProviderType.NOUS:
            return self.nous_adapter
        elif spec.provider == ModelProviderType.MOCK:
            return self.mock_adapter
        else:
            raise ModelRoutingError(f"No adapter registered for provider: {spec.provider}")
