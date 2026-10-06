"""ARYN packages root."""

from packages.runtime_adapters.hermes import HermesRuntimeAdapter
from packages.model_adapters.router import ModelRouter

def get_hermes_adapter():
    return HermesRuntimeAdapter

def get_model_router():
    return ModelRouter

__all__ = [
    "HermesRuntimeAdapter",
    "ModelRouter",
    "get_hermes_adapter",
    "get_model_router",
]
