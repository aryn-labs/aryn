"""Nous Research / Hermes model adapter for ARYN infrastructure."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from packages.contracts.model import ModelProviderType, ModelSpec


class NousModelAdapter:
    """Adapter for Nous Research and Hermes models."""

    SUPPORTED_MODELS: Dict[str, ModelSpec] = {
        "stealth/space-bunny-alpha": ModelSpec(
            provider=ModelProviderType.NOUS,
            model_id="stealth/space-bunny-alpha",
            display_name="Nous Space Bunny Alpha",
            context_window=32768,
            supports_tools=True,
            requires_api_key=False,
        ),
        "hermes-3-llama-3.1-8b": ModelSpec(
            provider=ModelProviderType.NOUS,
            model_id="hermes-3-llama-3.1-8b",
            display_name="Hermes 3 Llama 3.1 8B",
            context_window=131072,
            supports_tools=True,
            requires_api_key=True,
        ),
        "hermes-3-llama-3.1-70b": ModelSpec(
            provider=ModelProviderType.NOUS,
            model_id="hermes-3-llama-3.1-70b",
            display_name="Hermes 3 Llama 3.1 70B",
            context_window=131072,
            supports_tools=True,
            requires_api_key=True,
        ),
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or ""

    def get_spec(self, model_id: str) -> ModelSpec:
        if model_id not in self.SUPPORTED_MODELS:
            raise ValueError(f"Model '{model_id}' is not supported by Nous adapter. Supported: {list(self.SUPPORTED_MODELS.keys())}")
        return self.SUPPORTED_MODELS[model_id]

    def build_request_payload(self, prompt: str, system_instructions: Optional[str] = None, model_id: str = "stealth/space-bunny-alpha") -> Dict[str, Any]:
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
