"""Exceptions for database repository layer."""


class RepositoryError(Exception):
    """Base exception for repository operations."""
    pass


class EntityNotFoundError(RepositoryError):
    """Raised when a requested entity does not exist."""
    pass


class TenantIsolationError(RepositoryError):
    """Raised when an operation attempts to breach tenant or project boundaries."""
    pass


class DuplicateEntityError(RepositoryError):
    """Raised when an entity with unique constraint already exists."""
    pass


class InvalidStateTransitionError(RepositoryError):
    """Raised when an illegal run state transition is requested."""
    pass
