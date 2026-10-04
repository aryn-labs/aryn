"""Model adapters package (Python-compliant snake_case alias)."""

import importlib

_mod = importlib.import_module("packages.model-adapters")
ModelRouter = _mod.ModelRouter
ModelRoutingError = _mod.ModelRoutingError
GeminiModelAdapter = _mod.GeminiModelAdapter
NousModelAdapter = _mod.NousModelAdapter
MockModelAdapter = _mod.MockModelAdapter

__all__ = [
    "ModelRouter",
    "ModelRoutingError",
    "GeminiModelAdapter",
    "NousModelAdapter",
    "MockModelAdapter",
]
