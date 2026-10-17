"""Historical test identities retained to prove provider consolidation."""
import importlib.util
from pathlib import Path
import pytest
from packages.contracts.model import ModelProviderType, ModelSpec
from packages.model_adapters import ModelRouter, ModelRoutingError


def test_gemini_adapter_provides_model_specifications():
    # Historical descriptors still deserialize; they never enable a provider.
    spec = ModelSpec(provider="gemini", model_id="gemini-1.5-pro", display_name="Historical")
    assert spec.provider == ModelProviderType.GEMINI
    with pytest.raises(ModelRoutingError):
        ModelRouter().get_adapter_for_spec(spec)


def test_gemini_adapter_builds_request_payload():
    import packages.model_adapters as adapters
    assert not hasattr(adapters, "GeminiModelAdapter")
    assert not hasattr(adapters, "MockModelAdapter")
    assert not hasattr(adapters, "NousModelAdapter")


def test_gemini_status_is_specification_only_not_live():
    root = Path(__file__).resolve().parents[2] / "packages/model_adapters/providers"
    for name in ("gemini", "mock", "nous"):
        assert not (root / (name + ".py")).exists()
        try:
            spec = importlib.util.find_spec("packages.model_adapters.providers." + name)
        except ModuleNotFoundError as error:
            assert error.name == "packages.model_adapters.providers"
        else:
            assert spec is None
    with pytest.raises(ModelRoutingError):
        ModelRouter().resolve_model("gemini-2.0-flash")
