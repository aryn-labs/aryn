"""Agent Factory package (hyphenated directory compatibility alias)."""

from modules.agent_factory.service import (
    AgentFactoryService,
    ForbiddenToolError,
    UnpublishedVersionError,
    VersionImmutableError,
)

__all__ = [
    "AgentFactoryService",
    "ForbiddenToolError",
    "UnpublishedVersionError",
    "VersionImmutableError",
]
