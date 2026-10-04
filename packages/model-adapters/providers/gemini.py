"""Google Gemini model provider adapter for ARYN infrastructure.

Complies with ARYN-TECH-001 ADR-005.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from packages.contracts.model import ModelProviderType, ModelSpec


class GeminiModelAdapter:
    """Adapter for Google Gemini models."""

    SUPPORTED_MODELS: Dict[str, ModelSpec] = {
        "gemini-2.0-flash": ModelSpec(
            provider=ModelProviderType.GEMINI,
            model_id="gemini-2.0-flash",
            display_name="Google Gemini 2.0 Flash",
            context_window=1048576,
            supports_tools=True,
            requires_api_key=True,
        ),
        "gemini-1.5-pro": ModelSpec(
            provider=ModelProviderType.GEMINI,
            model_id="gemini-1.5-pro",
            display_name="Google Gemini 1.5 Pro",
            context_window=2097152,
            supports_tools=True,
            requires_api_key=True,
        ),
        "gemini-1.5-flash": ModelSpec(
            provider=ModelProviderType.GEMINI,
            model_id="gemini-1.5-flash",
            display_name="Google Gemini 1.5 Flash",
            context_window=1048576,
            supports_tools=True,
            requires_api_key=True,
        ),
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or ""

    def get_spec(self, model_id: str) -> ModelSpec:
        if model_id not in self.SUPPORTED_MODELS:
            raise ValueError(f"Model '{model_id}' is not supported by Gemini adapter. Supported: {list(self.SUPPORTED_MODELS.keys())}")
        return self.SUPPORTED_MODELS[model_id]

    def build_request_payload(self, prompt: str, system_instructions: Optional[str] = None, model_id: str = "gemini-2.0-flash") -> Dict[str, Any]:
        spec = self.get_spec(model_id)
        messages: List[Dict[str, str]] = []
        if system_instructions:
            messages.append({"role": "system", "content": system_instructions})
        messages.append({"role": "user", "content": prompt})

        return {
            "model": spec.model_id,
            "messages": messages,
            "provider": spec.provider.value,
        }
