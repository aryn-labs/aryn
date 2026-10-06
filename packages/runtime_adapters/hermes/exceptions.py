"""Exceptions for Hermes runtime adapter."""


class HermesAdapterError(Exception):
    """Base exception for Hermes runtime adapter."""
    pass


class RuntimeConnectionError(HermesAdapterError):
    """Raised when adapter cannot connect to Hermes gateway."""
    pass


class RuntimeAuthenticationError(HermesAdapterError):
    """Raised when Hermes rejects the API_SERVER_KEY / Bearer token."""
    pass


class RuntimeTimeoutError(HermesAdapterError):
    """Raised when an operation against Hermes times out."""
    pass


class RuntimeSecurityError(HermesAdapterError):
    """Raised when a security invariant or tool confinement check fails."""
    pass


class RunNotFoundError(HermesAdapterError):
    """Raised when a requested run_id is not found."""
    pass
