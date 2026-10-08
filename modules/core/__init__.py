"""ARYN Core domain package."""

from importlib import import_module

# Runtime-side sanitization must not load database/control-plane dependencies.
_EXPORTS = {
    "AuditLogger": "modules.core.audit.logger",
    "PermissionEngine": "modules.core.permissions.engine",
    "PermissionDeniedError": "modules.core.permissions.engine",
    "BudgetEngine": "modules.core.usage.engine",
    "BudgetExceededError": "modules.core.usage.engine",
    "RunCoordinator": "modules.core.workflows.coordinator",
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name]), name)
    globals()[name] = value
    return value

__all__ = [
    "AuditLogger",
    "PermissionEngine",
    "PermissionDeniedError",
    "BudgetEngine",
    "BudgetExceededError",
    "RunCoordinator",
]
