"""ARYN Core Permissions Engine.

Enforces role-based access control, tenant scoping, and project authorization.
Complies with ARYN-ARCH-001 Section 03 and ARYN-SEC-001.

Authoritatively derives permissions from database memberships under deny-by-default.
Caller-provided SecurityContext roles are untrusted and strictly ignored.
Note: Production environments require a trusted external Identity Provider (OIDC / mTLS)
to authenticate actor identity prior to context binding; this engine enforces the authorization boundary.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from database.connection import DatabaseManager
from database.schema import MembershipModel, ProjectModel
from packages.contracts.core import ActorType, PolicyDecision, SecurityContext


class PermissionDeniedError(Exception):
    """Raised when an action violates authorization policy."""
    pass


class PermissionEngine:
    """Authoritative server-side policy evaluator deriving permissions from database memberships."""

    ROLE_PERMISSIONS: Dict[str, Set[str]] = {
        "admin": {
            "run:create",
            "run:read",
            "run:cancel",
            "run:trace",
            "system:health",
            "system:capabilities",
            "blueprint:create",
            "version:create",
            "version:approve",
            "version:publish",
            "agent:assign",
        },
        "operator": {
            "run:create",
            "run:read",
            "run:cancel",
            "run:trace",
            "system:health",
            "blueprint:create",
            "version:create",
            "version:publish",
            "agent:assign",
        },
        "viewer": {
            "run:read",
            "run:trace",
            "system:health",
        },
    }

    # Actions strictly reserved for human actors; autonomous agents are forbidden
    HUMAN_ONLY_ACTIONS: Set[str] = {
        "version:approve",
        "version:publish",
    }

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db_manager = db_manager

    def evaluate(
        self,
        action: str,
        context: SecurityContext,
        target_org_id: str,
        target_project_id: Optional[str] = None,
    ) -> PolicyDecision:
        # 1. Deny-by-default: Organization identifier validation
        if not target_org_id or not context.organization_id:
            return PolicyDecision(
                allowed=False,
                reason="Authorization denied: Organization identifier cannot be empty.",
                matched_rules=["RULE_DENY_BY_DEFAULT", "RULE_TENANT_ISOLATION"],
            )

        # 2. Enforce tenant boundary
        if context.organization_id != target_org_id:
            return PolicyDecision(
                allowed=False,
                reason=f"Tenant boundary violation: context org '{context.organization_id}' does not match target org '{target_org_id}'.",
                matched_rules=["RULE_TENANT_ISOLATION"],
            )

        # 3. Actor-tenant consistency
        if context.actor.organization_id != target_org_id:
            return PolicyDecision(
                allowed=False,
                reason=f"Actor organization mismatch: actor org '{context.actor.organization_id}' does not match target org '{target_org_id}'.",
                matched_rules=["RULE_ACTOR_ORG_MISMATCH", "RULE_TENANT_ISOLATION"],
            )

        # 4. Project boundary and consistency
        if target_project_id is not None:
            if context.project_id != target_project_id:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Project boundary violation: context project '{context.project_id}' does not match target project '{target_project_id}'.",
                    matched_rules=["RULE_PROJECT_ISOLATION"],
                )
            if context.actor.project_id and context.actor.project_id != target_project_id:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Project boundary violation: actor project '{context.actor.project_id}' does not match target project '{target_project_id}'.",
                    matched_rules=["RULE_PROJECT_ISOLATION"],
                )

        # 5. Deny-by-default if authoritative membership database is not configured
        if self.db_manager is None:
            return PolicyDecision(
                allowed=False,
                reason="Authoritative membership store not configured (deny-by-default).",
                matched_rules=["RULE_DENY_BY_DEFAULT", "RULE_AUTH_STORE_UNAVAILABLE"],
            )

        # 6. Database verification: Project existence, Tenant scoping, and Membership validation
        effective_project_id = target_project_id or context.project_id
        with self.db_manager.session() as session:
            # 6a. Verify project belongs to target organization if project is specified
            if effective_project_id:
                proj = session.query(ProjectModel).filter_by(id=effective_project_id).first()
                if not proj:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Project '{effective_project_id}' does not exist.",
                        matched_rules=["RULE_PROJECT_NOT_FOUND"],
                    )
                if proj.organization_id != target_org_id:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Cross-tenant project violation: Project '{effective_project_id}' belongs to org '{proj.organization_id}', not target org '{target_org_id}'.",
                        matched_rules=["RULE_CROSS_TENANT_VIOLATION"],
                    )

            # 6b. Authoritative membership lookup
            member = (
                session.query(MembershipModel)
                .filter_by(organization_id=target_org_id, user_id=context.actor.actor_id)
                .first()
            )
            if not member:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Actor '{context.actor.actor_id}' has no membership in organization '{target_org_id}'.",
                    matched_rules=["RULE_MEMBERSHIP_REQUIRED"],
                )

            # 6c. Verify membership status (active vs revoked vs suspended)
            status = getattr(member, "status", "active")
            if status != "active":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Membership for actor '{context.actor.actor_id}' in org '{target_org_id}' is {status}.",
                    matched_rules=["RULE_MEMBERSHIP_INACTIVE"],
                )

            # 6d. Derive authoritative effective role — caller-supplied context.actor.roles is STRICTLY IGNORED
            effective_role = member.role.lower()

        # 7. Agent confinement: autonomous agents cannot perform governance/approval actions
        if context.actor.actor_type == ActorType.AGENT and action in self.HUMAN_ONLY_ACTIONS:
            return PolicyDecision(
                allowed=False,
                reason=f"Action '{action}' is strictly reserved for human operators (agents cannot perform governance/approval actions).",
                matched_rules=["RULE_AGENT_CONFINEMENT"],
            )

        # 8. Role-action authorization check against effective database role
        allowed_actions = self.ROLE_PERMISSIONS.get(effective_role, set())
        if action not in allowed_actions:
            return PolicyDecision(
                allowed=False,
                reason=f"Action '{action}' is not permitted for actor '{context.actor.actor_id}' with effective role '{effective_role}'.",
                matched_rules=["RULE_RBAC_ENFORCEMENT"],
            )

        return PolicyDecision(
            allowed=True,
            reason="Authorized by ARYN Core authoritative RBAC policy.",
            matched_rules=["RULE_RBAC_PERMITTED", "RULE_TENANT_VERIFIED", "RULE_MEMBERSHIP_VERIFIED"],
        )

    def enforce(
        self,
        action: str,
        context: SecurityContext,
        target_org_id: str,
        target_project_id: Optional[str] = None,
    ) -> None:
        decision = self.evaluate(action, context, target_org_id, target_project_id)
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason)
