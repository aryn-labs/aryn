"""ARYN Core Permissions Engine.

Enforces role-based access control, tenant scoping, and project authorization.
Complies with ARYN-ARCH-001 Section 03 and ARYN-SEC-001.

Authoritatively derives permissions from database memberships under deny-by-default.
Verifies trusted identity assertions at the Core boundary to prevent actor_id / actor_type forgery.
Enforces explicit project-level memberships for operators and viewers while maintaining org admin oversight.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from database.connection import DatabaseManager
from database.schema import MembershipModel, ProjectModel, ProjectMembershipModel
from packages.contracts.core import ActorType, PolicyDecision, SecurityContext
from modules.core.identity.binder import TrustedIdentityBinder


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
            "bench:accept_baseline",
            "version:publish",
            "agent:assign",
            "agent:rollback",
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
        "agent:rollback",
        "bench:accept_baseline",
        "version:approve",
        "version:publish",
    }

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        identity_binder: Optional[TrustedIdentityBinder] = None,
    ) -> None:
        self.db_manager = db_manager
        if identity_binder is not None:
            self.identity_binder = identity_binder
        else:
            try:
                self.identity_binder = TrustedIdentityBinder()
            except (ValueError, TypeError):
                self.identity_binder = None

    def evaluate(
        self,
        action: str,
        context: SecurityContext,
        target_org_id: str,
        target_project_id: Optional[str] = None,
    ) -> PolicyDecision:
        # 1. Authoritative Identity Binding Verification (Fail-closed on untrusted/forged actor claims)
        if self.identity_binder is None:
            return PolicyDecision(
                allowed=False,
                reason="Authorization denied: Core boundary missing trusted identity binder (fail-closed).",
                matched_rules=["RULE_IDENTITY_UNTRUSTED", "RULE_DENY_BY_DEFAULT"],
            )

        identity_decision = self.identity_binder.verify_context(context)
        if not identity_decision.allowed:
            return identity_decision

        # 2. Deny-by-default: Organization identifier validation
        if not target_org_id or not context.organization_id:
            return PolicyDecision(
                allowed=False,
                reason="Authorization denied: Organization identifier cannot be empty.",
                matched_rules=["RULE_DENY_BY_DEFAULT", "RULE_TENANT_ISOLATION"],
            )

        # 3. Enforce tenant boundary
        if context.organization_id != target_org_id:
            return PolicyDecision(
                allowed=False,
                reason=f"Tenant boundary violation: context org '{context.organization_id}' does not match target org '{target_org_id}'.",
                matched_rules=["RULE_TENANT_ISOLATION"],
            )

        # 4. Actor-tenant consistency
        if context.actor.organization_id != target_org_id:
            return PolicyDecision(
                allowed=False,
                reason=f"Actor organization mismatch: actor org '{context.actor.organization_id}' does not match target org '{target_org_id}'.",
                matched_rules=["RULE_ACTOR_ORG_MISMATCH", "RULE_TENANT_ISOLATION"],
            )

        # 5. Project boundary and consistency
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

        # 6. Deny-by-default if authoritative membership database is not configured
        if self.db_manager is None:
            return PolicyDecision(
                allowed=False,
                reason="Authoritative membership store not configured (deny-by-default).",
                matched_rules=["RULE_DENY_BY_DEFAULT", "RULE_AUTH_STORE_UNAVAILABLE"],
            )

        # 7. Database verification: Project existence, Tenant scoping, and Hierarchical Membership validation
        effective_project_id = target_project_id or context.project_id
        with self.db_manager.session() as session:
            # 7a. Verify project belongs to target organization if project is specified
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

            # 7b. Authoritative organization membership lookup
            org_member = (
                session.query(MembershipModel)
                .filter_by(organization_id=target_org_id, user_id=context.actor.actor_id)
                .first()
            )
            if not org_member:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Actor '{context.actor.actor_id}' has no membership in organization '{target_org_id}'.",
                    matched_rules=["RULE_MEMBERSHIP_REQUIRED"],
                )

            # 7c. Verify organization membership status (active vs revoked vs suspended)
            org_status = getattr(org_member, "status", "active")
            if org_status != "active":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Membership for actor '{context.actor.actor_id}' in org '{target_org_id}' is {org_status}.",
                    matched_rules=["RULE_MEMBERSHIP_INACTIVE"],
                )

            org_role = org_member.role.lower()

            # 7d. Project-Level Authorization Enforcement:
            # - Organization Admin has organization-wide oversight across all projects in that organization.
            # - Operators and Viewers MUST have an explicit, active ProjectMembership record for the target project.
            if effective_project_id:
                if org_role == "admin":
                    effective_role = "admin"
                else:
                    proj_member = (
                        session.query(ProjectMembershipModel)
                        .filter_by(
                            project_id=effective_project_id,
                            user_id=context.actor.actor_id,
                        )
                        .first()
                    )
                    if not proj_member:
                        return PolicyDecision(
                            allowed=False,
                            reason=(
                                f"Project authorization denied: Actor '{context.actor.actor_id}' "
                                f"is not an authorized member of project '{effective_project_id}' in organization '{target_org_id}'."
                            ),
                            matched_rules=["RULE_PROJECT_MEMBERSHIP_REQUIRED", "RULE_DENY_BY_DEFAULT"],
                        )

                    p_status = getattr(proj_member, "status", "active")
                    if p_status != "active":
                        return PolicyDecision(
                            allowed=False,
                            reason=(
                                f"Project authorization denied: Project membership for actor '{context.actor.actor_id}' "
                                f"in project '{effective_project_id}' is {p_status}."
                            ),
                            matched_rules=["RULE_PROJECT_MEMBERSHIP_INACTIVE"],
                        )

                    effective_role = proj_member.role.lower()
            else:
                effective_role = org_role

        # 8. Agent confinement: autonomous agents cannot perform governance/approval actions
        if context.actor.actor_type != ActorType.USER and action in self.HUMAN_ONLY_ACTIONS:
            return PolicyDecision(
                allowed=False,
                reason=f"Action '{action}' is strictly reserved for human operators (agents cannot perform governance/approval actions).",
                matched_rules=["RULE_AGENT_CONFINEMENT"],
            )

        # 9. Role-action authorization check against effective database role
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
            matched_rules=["RULE_RBAC_PERMITTED", "RULE_TENANT_VERIFIED", "RULE_MEMBERSHIP_VERIFIED", "RULE_IDENTITY_VERIFIED"],
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
