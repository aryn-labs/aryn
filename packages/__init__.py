"""ARYN packages root."""

import importlib

# Dynamic convenience exports for hyphenated packages
def get_hermes_adapter():
    return importlib.import_module("packages.runtime-adapters.hermes").HermesRuntimeAdapter

def get_model_router():
    return importlib.import_module("packages.model-adapters").ModelRouter
