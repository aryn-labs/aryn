"""Unit tests for ModelRouter and provider abstractions."""

import pytest
import importlib
from packages.contracts.model import ModelProviderType, ModelRoutingConfig

model_adapters = importlib.import_module("packages.model-adapters")
ModelRouter = model_adapters.ModelRouter
ModelRoutingError = model_adapters.ModelRoutingError


def test_model_router_resolves_configured_model():
    router = ModelRouter()
    spec = router.resolve_model("mock-fast")
    assert spec.provider == ModelProviderType.MOCK
    assert spec.model_id == "mock-fast"


def test_model_router_forbids_silent_fallback_on_unallowed_model():
    config = ModelRoutingConfig(
        active_provider=ModelProviderType.GEMINI,
        active_model="gemini-2.0-flash",
        allowed_models=["gemini-2.0-flash"],
        allow_fallback=False,
    )
    router = ModelRouter(config=config)

    with pytest.raises(ModelRoutingError) as exc_info:
        router.resolve_model("unregistered-super-model")

    assert "is not in the allowed routing list" in str(exc_info.value)
    assert "Silent fallback is forbidden" in str(exc_info.value)


def test_gemini_payload_builder():
    from packages.model_adapters import GeminiModelAdapter
    adapter = GeminiModelAdapter()
    spec = adapter.get_spec("gemini-1.5-pro")
    payload = adapter.build_request_payload(
        prompt="Analyze data",
        system_instructions="You are ARYN analyst",
        model_id=spec.model_id,
    )

    assert payload["model"] == "gemini-1.5-pro"
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"


def test_mock_adapter_offline_deterministic():
    router = ModelRouter()
    spec = router.resolve_model("mock-fast")
    adapter = router.get_adapter_for_spec(spec)
    payload = adapter.build_request_payload("hello", model_id="mock-fast")

    assert payload["canned_response"] == "mocked response"
