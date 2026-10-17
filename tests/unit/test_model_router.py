"""Unit tests for ModelRouter and provider abstractions."""

import pytest
from packages.contracts.model import ModelProviderType, ModelRoutingConfig
from packages.model_adapters import ModelRouter, ModelRoutingError
from tests.model_fixtures import offline_model_router


def test_model_router_resolves_configured_model():
    router = offline_model_router()
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
    from packages.contracts.model import ModelSpec
    spec = ModelSpec(provider=ModelProviderType.NINE_ROUTER, model_id="gemini-1.5-pro", display_name="Gateway model")
    router = ModelRouter(catalog={spec.model_id: spec})
    assert router.resolve_model(spec.model_id) == spec
    with pytest.raises(ModelRoutingError):
        router.get_adapter_for_spec(spec)


def test_mock_adapter_offline_deterministic():
    router = ModelRouter()
    assert router.catalog == {}
    with pytest.raises(ModelRoutingError):
        router.resolve_model("mock-fast")
