"""Explicit live opt-in support. Importing this helper dispatches no inference."""
import os
import pytest
from packages.contracts.model import ModelProviderType, ModelSpec
from packages.model_adapters import ModelRouter


async def selected_live_model(adapter):
    model = os.getenv("ARYN_LIVE_MODEL", "")
    if not model:
        pytest.skip("An explicit ARYN_LIVE_MODEL is required; no default/substitution.")
    await adapter.require_model_available(model)
    snapshot = await adapter.discover_models(refresh=True)
    assert snapshot.discovery_valid and any(m["model_id"] == model for m in snapshot.models)
    spec = ModelSpec(provider=ModelProviderType.NINE_ROUTER, model_id=model, display_name=model,
                     requires_api_key=False)
    return model, ModelRouter(catalog={model: spec})
