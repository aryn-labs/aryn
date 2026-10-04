"""Runtime adapters package (Python-compliant snake_case alias)."""

import importlib

_hermes = importlib.import_module("packages.runtime-adapters.hermes")
HermesRuntimeAdapter = _hermes.HermesRuntimeAdapter
HermesAdapterError = _hermes.HermesAdapterError
RunNotFoundError = _hermes.RunNotFoundError
RuntimeAuthenticationError = _hermes.RuntimeAuthenticationError
RuntimeConnectionError = _hermes.RuntimeConnectionError
RuntimeSecurityError = _hermes.RuntimeSecurityError
RuntimeTimeoutError = _hermes.RuntimeTimeoutError

__all__ = [
    "HermesRuntimeAdapter",
    "HermesAdapterError",
    "RunNotFoundError",
    "RuntimeAuthenticationError",
    "RuntimeConnectionError",
    "RuntimeSecurityError",
    "RuntimeTimeoutError",
]
