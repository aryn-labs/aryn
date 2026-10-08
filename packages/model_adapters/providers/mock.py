"""Mock provider adapter for isolated, deterministic offline tests."""

from __future__ import annotations

from typing import Any, Dict, Optional
from packages.contracts.model import ModelProviderType, ModelSpec


class MockModelAdapter:
    """Mock adapter for offline tests and evaluation."""

    SUPPORTED_MODELS: Dict[str, ModelSpec] = {
        "mock-fast": ModelSpec(
            provider=ModelProviderType.MOCK,
            model_id="mock-fast",
            display_name="Mock Fast Model",
            context_window=8192,
            supports_tools=False,
            requires_api_key=False,
        ),
        "mock-reasoning": ModelSpec(
            provider=ModelProviderType.MOCK,
            model_id="mock-reasoning",
            display_name="Mock Reasoning Model",
            context_window=32768,
            supports_tools=False,
            requires_api_key=False,
        ),
    }

    def __init__(self, canned_response: str = "mocked response") -> None:
        self.canned_response = canned_response

    def get_spec(self, model_id: str) -> ModelSpec:
        if model_id not in self.SUPPORTED_MODELS:
            raise ValueError(f"Model '{model_id}' is not supported by Mock adapter.")
        return self.SUPPORTED_MODELS[model_id]

    def build_request_payload(self, prompt: str, system_instructions: Optional[str] = None, model_id: str = "mock-fast") -> Dict[str, Any]:
        return {
            "model": model_id,
            "prompt": prompt,
            "canned_response": self.canned_response,
        }
