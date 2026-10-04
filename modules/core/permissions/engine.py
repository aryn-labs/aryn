"""ARYN Core Permissions Engine.

Enforces role-based access control, tenant scoping, and project authorization.
Complies with ARYN-ARCH-001 Section 03 and ARYN-SEC-001.
"""

from __future__ import annotations

from typing import Dict, List, Set
from packages.contracts.core import PolicyDecision, SecurityContext


class PermissionDeniedError(Exception):
    """Raised when an action violates authorization policy."""
    pass


class PermissionEngine:
    """Authoritative server-side policy evaluator."""

    ROLE_PERMISSIONS: Dict[str, Set[str]] = {
        "admin": {"run:create", "run:read", "run:cancel", "run:trace", "system:health", "system:capabilities"},
        "operator": {"run:create", "run:read", "run:cancel", "run:trace", "system:health"},
        "viewer": {"run:read", "run:trace", "system:health"},
    }

    def evaluate(self, action: str, context: SecurityContext, target_org_id: str, target_project_id: str | None = None) -> PolicyDecision:
        # 1. Enforce tenant boundary
        if not context.validate_ownership(target_org_id, target_project_id):
            return PolicyDecision(
                allowed=False,
                reason=f"Tenant boundary violation: context org '{context.organization_id}' does not match target org '{target_org_id}'.",
                matched_rules=["RULE_TENANT_ISOLATION"],
            )

        # 2. Check roles and action permissions
        actor_roles = context.actor.roles
        allowed_actions: Set[str] = set()
        for role in actor_roles:
            allowed_actions.update(self.ROLE_PERMISSIONS.get(role, set()))

        if action not in allowed_actions:
            return PolicyDecision(
                allowed=False,
                reason=f"Action '{action}' is not permitted for actor '{context.actor.actor_id}' with roles {actor_roles}.",
                matched_rules=["RULE_RBAC_ENFORCEMENT"],
            )

        return PolicyDecision(
            allowed=True,
            reason="Authorized by ARYN Core policy.",
            matched_rules=["RULE_RBAC_PERMITTED", "RULE_TENANT_VERIFIED"],
        )

    def enforce(self, action: str, context: SecurityContext, target_org_id: str, target_project_id: str | None = None) -> None:
        decision = self.evaluate(action, context, target_org_id, target_project_id)
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason)
