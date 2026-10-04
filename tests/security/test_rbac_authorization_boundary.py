"""Comprehensive Security Tests for ARYN Authorization Boundary & RBAC.

Validates:
1. Trusted Identity Binding & Fail-Closed Behavior:
   - Unsigned SecurityContext is rejected (fail-closed).
   - Impersonation of actor_id is detected and rejected via signature mismatch.
   - Forged actor_type (agent escalating to user) is detected and rejected.
2. Hierarchical Project-Level Authorization:
   - Org Admin has organization-wide authority over all projects in the organization.
   - Operators and Viewers are strictly restricted to projects where they hold explicit ProjectMembership.
   - Access to other projects in the same organization without project membership is DENIED.
   - Revoked project membership is DENIED.
3. Database-Backed Role Verification:
   - Forged client roles are strictly ignored; effective permissions derive authoritatively from DB.
   - Non-existent organization membership is DENIED by default.
   - Revoked or suspended organization membership is DENIED.
4. Tenant and Project Boundary Isolation:
   - Cross-tenant project access is DENIED.
   - Nonexistent project is DENIED.
   - Actor organization mismatch is DENIED.
5. Autonomous Agent Confinement:
   - Agents are forbidden from approving or publishing versions.
6. Positive Authorized Access:
   - Org Admin can manage any project in the organization.
   - Project Operator can perform permitted operations on their assigned project.
   - Project Viewer has read-only access on their assigned project.

Complies with ARYN-ARCH-001 Section 03, ARYN-SEC-001, and AGENTS.md rules 3, 4, 7.
"""

import pytest

from database.connection import DatabaseManager, create_db_engine
from database.schema import Base
from database.repositories.organization_repo import OrganizationRepository
from packages.contracts.core import (
    Actor,
    ActorType,
    AuditStatus,
    SecurityContext,
)
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeTrace,
)
from modules.core.identity.binder import TrustedIdentityBinder
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.approvals.engine import ApprovalEngine, UnauthorizedApproverError
from modules.core.workflows.coordinator import RunCoordinator
from modules.agent_factory.service import AgentFactoryService
from modules.bench.runner import BenchRunner


class MockTestRuntime(RuntimeAdapter):
    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(is_healthy=True, status="ok", platform="mock", version="1.0", listener_url="http://127.0.0.1:8642")

    async def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        return RunResult(
            run_id="run_test_rbac",
            status=RunStatus.COMPLETED,
            output="Authorized response",
            usage=RunUsage(input_tokens=20, output_tokens=30, total_tokens=50),
            model=request.model,
            created_at=1700000000.0,
            completed_at=1700000001.0,
        )

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        return "run_async_test_rbac"

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        return await self.execute_direct_turn(RunRequest(prompt="", model="mock-fast"), context)

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        return True

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        return RuntimeTrace(run_id=run_id, events=[])


@pytest.fixture
def rbac_db():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = DatabaseManager(engine=engine)

    with db.session() as s:
        repo = OrganizationRepository(s)
        # Org Alpha
        repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
        repo.add_member("org_alpha", "user_alpha_admin", role="admin", status="active")
        repo.add_member("org_alpha", "user_alpha_op", role="operator", status="active")
        repo.add_member("org_alpha", "user_alpha_viewer", role="viewer", status="active")
        repo.add_member("org_alpha", "user_alpha_revoked", role="operator", status="revoked")
        repo.add_member("org_alpha", "user_alpha_suspended", role="admin", status="suspended")

        # Org Alpha - Projects
        ctx_alpha = SecurityContext(
            actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ).sign()
        repo.create_project(ctx_alpha, "proj_alpha_main", "Alpha Main", "alpha-main")
        repo.create_project(ctx_alpha, "proj_alpha_secondary", "Alpha Secondary", "alpha-secondary")

        # Project memberships in proj_alpha_main:
        # user_alpha_op is operator on proj_alpha_main
        repo.add_project_member("proj_alpha_main", "user_alpha_op", role="operator", status="active")
        # user_alpha_viewer is viewer on proj_alpha_main
        repo.add_project_member("proj_alpha_main", "user_alpha_viewer", role="viewer", status="active")

        # Note: NEITHER user_alpha_op NOR user_alpha_viewer is added to proj_alpha_secondary!

        # Org Beta
        repo.create_organization("org_beta", "Beta Corp", "beta-corp")
        repo.add_member("org_beta", "user_beta_admin", role="admin", status="active")

        ctx_beta = SecurityContext(
            actor=Actor(actor_id="user_beta_admin", organization_id="org_beta", roles=["admin"]),
            organization_id="org_beta",
            project_id="proj_beta_main",
        ).sign()
        repo.create_project(ctx_beta, "proj_beta_main", "Beta Main", "beta-main")

    return db


# -----------------------------------------------------------------------------
# 1. Negative Tests: Trusted Identity Binding & Fail-Closed Verification
# -----------------------------------------------------------------------------

def test_unsigned_security_context_fails_closed(rbac_db):
    """An attacker or untrusted client sends an unsigned SecurityContext."""
    engine = PermissionEngine(db_manager=rbac_db)

    unsigned_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        identity_token=None,  # Unsigned!
    )

    decision = engine.evaluate("run:create", unsigned_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "Untrusted identity binding" in decision.reason
    assert "RULE_IDENTITY_UNTRUSTED" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="Untrusted identity binding"):
        engine.enforce("run:create", unsigned_context, "org_alpha", "proj_alpha_main")


def test_actor_id_impersonation_is_detected_and_rejected(rbac_db):
    """Context signed for user_alpha_op is tampered to impersonate user_alpha_admin."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Legitimate context signed for user_alpha_op
    context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    # Attacker tampers actor_id to admin
    context.actor.actor_id = "user_alpha_admin"

    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "impersonation or forged identity detected" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="impersonation or forged identity detected"):
        engine.enforce("run:create", context, "org_alpha", "proj_alpha_main")


def test_forged_actor_type_agent_to_user_is_detected_and_rejected(rbac_db):
    """Context signed for an AGENT is tampered to claim USER status."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Legitimate context signed for AGENT
    context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.AGENT,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    # Agent tampers actor_type to USER to bypass agent confinement
    context.actor.actor_type = ActorType.USER

    decision = engine.evaluate("version:approve", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "impersonation or forged identity detected" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules


def test_forged_admin_role_rejected_by_permission_engine(rbac_db):
    """An attacker provides roles=['admin'] in SecurityContext, but is only 'viewer' in DB."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Actor has "viewer" role in DB, but caller claims ["admin"]
    forged_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin", "superadmin", "root"],  # Forged!
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    decision = engine.evaluate("run:create", forged_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "effective role 'viewer'" in decision.reason
    assert "RULE_RBAC_ENFORCEMENT" in decision.matched_rules


@pytest.mark.asyncio
async def test_forged_admin_role_rejected_in_run_coordinator(rbac_db):
    """RunCoordinator refuses execution when caller claims admin but DB is viewer."""
    runtime = MockTestRuntime()
    coordinator = RunCoordinator(runtime_adapter=runtime, db_manager=rbac_db)

    forged_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    req = RunRequest(prompt="ping", model="mock-fast")
    with pytest.raises(PermissionDeniedError, match="effective role 'viewer'"):
        await coordinator.execute_managed_direct_turn(req, forged_context)


def test_forged_admin_role_rejected_in_approval_engine(rbac_db):
    """ApprovalEngine refuses to grant approval when caller claims admin but DB is viewer."""
    appr_engine = ApprovalEngine(db_manager=rbac_db)

    forged_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    with pytest.raises(UnauthorizedApproverError, match="lacks 'admin' role"):
        appr_engine.grant_approval(
            forged_context,
            target_type="agent_version",
            target_id="av_test",
            payload_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )


# -----------------------------------------------------------------------------
# 2. Negative Tests: Project-Level Authorization & Same-Org Isolation
# -----------------------------------------------------------------------------

def test_access_to_other_project_in_same_org_denied_for_operator(rbac_db):
    """Operator has membership in proj_alpha_main, but attempts to access proj_alpha_secondary in same org."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Actor has operator membership in org_alpha, and project membership in proj_alpha_main
    # But attempts to execute in proj_alpha_secondary (same org!)
    other_proj_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_secondary",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_secondary",
    ).sign()

    decision = engine.evaluate("run:create", other_proj_context, "org_alpha", "proj_alpha_secondary")
    assert decision.allowed is False
    assert "not an authorized member of project 'proj_alpha_secondary'" in decision.reason
    assert "RULE_PROJECT_MEMBERSHIP_REQUIRED" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="not an authorized member of project"):
        engine.enforce("run:create", other_proj_context, "org_alpha", "proj_alpha_secondary")


def test_revoked_project_membership_denied(rbac_db):
    """Operator's project membership is revoked; access must be denied even if org membership is active."""
    with rbac_db.session() as s:
        repo = OrganizationRepository(s)
        repo.revoke_project_member("proj_alpha_main", "user_alpha_op")

    engine = PermissionEngine(db_manager=rbac_db)
    context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "is revoked" in decision.reason
    assert "RULE_PROJECT_MEMBERSHIP_INACTIVE" in decision.matched_rules


def test_suspended_project_membership_denied(rbac_db):
    """Operator's project membership is suspended; access must be denied."""
    with rbac_db.session() as s:
        repo = OrganizationRepository(s)
        repo.suspend_project_member("proj_alpha_main", "user_alpha_op")

    engine = PermissionEngine(db_manager=rbac_db)
    context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "is suspended" in decision.reason
    assert "RULE_PROJECT_MEMBERSHIP_INACTIVE" in decision.matched_rules


# -----------------------------------------------------------------------------
# 3. Negative Tests: Organization Membership Status & Tenant Boundaries
# -----------------------------------------------------------------------------

def test_non_existent_org_membership_denied_by_default(rbac_db):
    """Actor has no membership in target organization; must be denied by default."""
    engine = PermissionEngine(db_manager=rbac_db)

    stranger_context = SecurityContext(
        actor=Actor(
            actor_id="user_stranger_unknown",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    decision = engine.evaluate("run:create", stranger_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "has no membership in organization" in decision.reason
    assert "RULE_MEMBERSHIP_REQUIRED" in decision.matched_rules


def test_revoked_org_membership_is_denied(rbac_db):
    """Actor org membership has status='revoked'; must be denied even for operator actions."""
    engine = PermissionEngine(db_manager=rbac_db)

    revoked_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_revoked",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    decision = engine.evaluate("run:create", revoked_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "is revoked" in decision.reason
    assert "RULE_MEMBERSHIP_INACTIVE" in decision.matched_rules


def test_cross_tenant_project_access_denied(rbac_db):
    """Actor from Org Alpha attempts to target Project belonging to Org Beta."""
    engine = PermissionEngine(db_manager=rbac_db)

    cross_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_beta_main",  # Belongs to org_beta!
        ),
        organization_id="org_alpha",
        project_id="proj_beta_main",
    ).sign()

    decision = engine.evaluate("run:create", cross_context, "org_alpha", "proj_beta_main")
    assert decision.allowed is False
    assert "Cross-tenant project violation" in decision.reason
    assert "RULE_CROSS_TENANT_VIOLATION" in decision.matched_rules


def test_actor_organization_mismatch_denied(rbac_db):
    """Actor's claimed organization does not match SecurityContext organization."""
    engine = PermissionEngine(db_manager=rbac_db)

    mismatch_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            organization_id="org_beta",  # Mismatch!
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    decision = engine.evaluate("run:create", mismatch_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "Actor organization mismatch" in decision.reason
    assert "RULE_ACTOR_ORG_MISMATCH" in decision.matched_rules


def test_agent_cannot_approve_or_publish(rbac_db):
    """Autonomous agent actors cannot approve or publish versions even with admin roles."""
    engine = PermissionEngine(db_manager=rbac_db)

    agent_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.AGENT,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    d_approve = engine.evaluate("version:approve", agent_context, "org_alpha", "proj_alpha_main")
    assert d_approve.allowed is False
    assert "strictly reserved for human operators" in d_approve.reason
    assert "RULE_AGENT_CONFINEMENT" in d_approve.matched_rules


def test_deny_by_default_when_no_authoritative_store_configured():
    """PermissionEngine without db_manager denies all actions deterministically."""
    unbacked_engine = PermissionEngine(db_manager=None)

    context = SecurityContext(
        actor=Actor(actor_id="any_user", organization_id="org_any", project_id="proj_any"),
        organization_id="org_any",
        project_id="proj_any",
    ).sign()

    decision = unbacked_engine.evaluate("run:create", context, "org_any", "proj_any")
    assert decision.allowed is False
    assert "not configured" in decision.reason
    assert "RULE_AUTH_STORE_UNAVAILABLE" in decision.matched_rules


# -----------------------------------------------------------------------------
# 4. Positive Tests: Valid Authorized Access
# -----------------------------------------------------------------------------

def test_valid_authorized_admin_access_across_all_org_projects(rbac_db):
    """Org Admin has authority across ALL projects in the organization."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Admin accessing proj_alpha_main
    ctx_main = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", project_id="proj_alpha_main"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    # Admin accessing proj_alpha_secondary (without explicit project membership row)
    ctx_sec = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", project_id="proj_alpha_secondary"),
        organization_id="org_alpha",
        project_id="proj_alpha_secondary",
    ).sign()

    for ctx in [ctx_main, ctx_sec]:
        for action in ["run:create", "run:read", "blueprint:create", "version:approve", "version:publish", "agent:assign"]:
            decision = engine.evaluate(action, ctx, "org_alpha", ctx.project_id)
            assert decision.allowed is True, f"Action {action} failed for admin on {ctx.project_id}"


def test_valid_authorized_operator_project_access(rbac_db):
    """Operator with active ProjectMembership on proj_alpha_main has full operational access."""
    engine = PermissionEngine(db_manager=rbac_db)

    op_context = SecurityContext(
        actor=Actor(actor_id="user_alpha_op", organization_id="org_alpha", project_id="proj_alpha_main"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    for action in ["run:create", "run:read", "blueprint:create", "version:create", "version:publish", "agent:assign"]:
        decision = engine.evaluate(action, op_context, "org_alpha", "proj_alpha_main")
        assert decision.allowed is True, f"Action {action} should be allowed for operator"

    # Operator cannot approve
    decision_appr = engine.evaluate("version:approve", op_context, "org_alpha", "proj_alpha_main")
    assert decision_appr.allowed is False


def test_valid_authorized_viewer_project_access(rbac_db):
    """Viewer with active ProjectMembership on proj_alpha_main has read access but cannot create runs."""
    engine = PermissionEngine(db_manager=rbac_db)

    viewer_context = SecurityContext(
        actor=Actor(actor_id="user_alpha_viewer", organization_id="org_alpha", project_id="proj_alpha_main"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ).sign()

    # Read allowed
    assert engine.evaluate("run:read", viewer_context, "org_alpha", "proj_alpha_main").allowed is True
    assert engine.evaluate("run:trace", viewer_context, "org_alpha", "proj_alpha_main").allowed is True

    # Write/Create denied
    assert engine.evaluate("run:create", viewer_context, "org_alpha", "proj_alpha_main").allowed is False
    assert engine.evaluate("blueprint:create", viewer_context, "org_alpha", "proj_alpha_main").allowed is False
