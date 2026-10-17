"""Explicit offline catalog composition. Never a production provider or fallback."""
from packages.contracts.model import ModelProviderType, ModelSpec
from packages.model_adapters import ModelRouter


def offline_model_router():
    return ModelRouter(catalog={name: ModelSpec(provider=ModelProviderType.MOCK,
        model_id=name, display_name=name, requires_api_key=False)
        for name in ("mock-fast", "mock-reasoning")})
