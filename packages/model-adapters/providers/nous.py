"""Deprecated descriptor import retained for compatibility; live routing belongs to 9Router."""

from typing import Dict
from packages.contracts.model import ModelSpec


class NousModelAdapter:
    """No legacy catalog, credentials, default model or invocation path."""

    SUPPORTED_MODELS: Dict[str, ModelSpec] = {}

    def get_spec(self, model_id: str) -> ModelSpec:
        raise ValueError("Discover models through 9Router; the legacy Nous catalog is unavailable.")

    def build_request_payload(self, prompt: str, system_instructions=None, *, model_id: str):
        self.get_spec(model_id)
