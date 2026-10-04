"""Comprehensive Security Tests for ARYN Authorization Boundary & RBAC.

Validates:
1. Forged admin role rejection (effective role derived strictly from DB membership, caller roles ignored).
2. Non-existent membership denial by default.
3. Revoked and suspended membership denial.
4. Unauthorized cross-tenant and project mismatch denial.
5. Actor and organization consistency verification.
6. Autonomous agent privilege escalation prevention (no self-approval or publish).
7. Deny-by-default when authoritative store is unavailable.
8. Valid authorized access for admin, operator, and viewer roles across Core and Agent Factory.

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

        ctx_alpha = SecurityContext(
            actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        )
        repo.create_project(ctx_alpha, "proj_alpha_main", "Alpha Main", "alpha-main")

        # Org Beta
        repo.create_organization("org_beta", "Beta Corp", "beta-corp")
        repo.add_member("org_beta", "user_beta_admin", role="admin", status="active")

        ctx_beta = SecurityContext(
            actor=Actor(actor_id="user_beta_admin", organization_id="org_beta", roles=["admin"]),
            organization_id="org_beta",
            project_id="proj_beta_main",
        )
        repo.create_project(ctx_beta, "proj_beta_main", "Beta Main", "beta-main")

    return db


# -----------------------------------------------------------------------------
# 1. Negative Test: Forged Admin Roles
# -----------------------------------------------------------------------------

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
    )

    decision = engine.evaluate("run:create", forged_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "effective role 'viewer'" in decision.reason
    assert "RULE_RBAC_ENFORCEMENT" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="effective role 'viewer'"):
        engine.enforce("run:create", forged_context, "org_alpha", "proj_alpha_main")


@pytest.mark.asyncio
async def test_forged_admin_role_rejected_in_run_coordinator(rbac_db):
    """RunCoordinator refuses execution when caller claims admin but DB is viewer."""
    runtime = MockTestRuntime()
    coordinator = RunCoordinator(runtime_adapter=runtime, db_manager=rbac_db)

    forged_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin"],  # Forged!
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

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
            roles=["admin"],  # Forged!
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    with pytest.raises(UnauthorizedApproverError, match="lacks 'admin' role"):
        appr_engine.grant_approval(
            forged_context,
            target_type="agent_version",
            target_id="av_test",
            payload_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )


def test_forged_admin_role_rejected_in_agent_factory(rbac_db):
    """AgentFactoryService rejects blueprint creation from forged admin."""
    bench = BenchRunner(runtime_adapter=MockTestRuntime())
    factory = AgentFactoryService(db_manager=rbac_db, bench_runner=bench)

    forged_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin"],  # Forged!
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    with pytest.raises(PermissionDeniedError, match="effective role 'viewer'"):
        factory.create_blueprint(forged_context, "Malicious Agent", "malicious-agent")


# -----------------------------------------------------------------------------
# 2. Negative Test: Non-Existent Membership (Deny-by-Default)
# -----------------------------------------------------------------------------

def test_non_existent_membership_denied_by_default(rbac_db):
    """Actor has no membership in target organization; must be denied by default."""
    engine = PermissionEngine(db_manager=rbac_db)

    stranger_context = SecurityContext(
        actor=Actor(
            actor_id="user_stranger_unknown",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    decision = engine.evaluate("run:create", stranger_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "has no membership in organization" in decision.reason
    assert "RULE_MEMBERSHIP_REQUIRED" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="has no membership"):
        engine.enforce("run:create", stranger_context, "org_alpha", "proj_alpha_main")


# -----------------------------------------------------------------------------
# 3. Negative Test: Revoked and Suspended Memberships
# -----------------------------------------------------------------------------

def test_revoked_membership_is_denied(rbac_db):
    """Actor membership has status='revoked'; must be denied even for operator actions."""
    engine = PermissionEngine(db_manager=rbac_db)

    revoked_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_revoked",
            actor_type=ActorType.USER,
            roles=["operator"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    decision = engine.evaluate("run:create", revoked_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "is revoked" in decision.reason
    assert "RULE_MEMBERSHIP_INACTIVE" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="is revoked"):
        engine.enforce("run:create", revoked_context, "org_alpha", "proj_alpha_main")


def test_suspended_membership_is_denied(rbac_db):
    """Actor membership has status='suspended'; must be denied even if role is admin."""
    engine = PermissionEngine(db_manager=rbac_db)

    suspended_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_suspended",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    decision = engine.evaluate("version:approve", suspended_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "is suspended" in decision.reason
    assert "RULE_MEMBERSHIP_INACTIVE" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="is suspended"):
        engine.enforce("version:approve", suspended_context, "org_alpha", "proj_alpha_main")


# -----------------------------------------------------------------------------
# 4. Negative Test: Unauthorized Cross-Tenant and Mismatched Projects
# -----------------------------------------------------------------------------

def test_cross_tenant_project_access_denied(rbac_db):
    """Actor from Org Alpha attempts to target Project belonging to Org Beta."""
    engine = PermissionEngine(db_manager=rbac_db)

    cross_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_beta_main",  # Belongs to org_beta!
        ),
        organization_id="org_alpha",
        project_id="proj_beta_main",
    )

    decision = engine.evaluate("run:create", cross_context, "org_alpha", "proj_beta_main")
    assert decision.allowed is False
    assert "Cross-tenant project violation" in decision.reason
    assert "RULE_CROSS_TENANT_VIOLATION" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="Cross-tenant project violation"):
        engine.enforce("run:create", cross_context, "org_alpha", "proj_beta_main")


def test_nonexistent_project_is_denied(rbac_db):
    """Actor targets a nonexistent project ID."""
    engine = PermissionEngine(db_manager=rbac_db)

    bad_proj_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_phantom_fake",
        ),
        organization_id="org_alpha",
        project_id="proj_phantom_fake",
    )

    decision = engine.evaluate("run:create", bad_proj_context, "org_alpha", "proj_phantom_fake")
    assert decision.allowed is False
    assert "does not exist" in decision.reason
    assert "RULE_PROJECT_NOT_FOUND" in decision.matched_rules


def test_actor_organization_mismatch_denied(rbac_db):
    """Actor's claimed organization does not match SecurityContext organization."""
    engine = PermissionEngine(db_manager=rbac_db)

    mismatch_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_beta",  # Mismatch!
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    decision = engine.evaluate("run:create", mismatch_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "Actor organization mismatch" in decision.reason
    assert "RULE_ACTOR_ORG_MISMATCH" in decision.matched_rules


# -----------------------------------------------------------------------------
# 5. Negative Test: Autonomous Agent Privilege Escalation
# -----------------------------------------------------------------------------

def test_agent_cannot_approve_or_publish(rbac_db):
    """Autonomous agent actors cannot approve or publish versions even with admin roles."""
    engine = PermissionEngine(db_manager=rbac_db)

    agent_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",  # points to admin member ID
            actor_type=ActorType.AGENT,    # but is an AGENT
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    # Agent cannot approve
    d_approve = engine.evaluate("version:approve", agent_context, "org_alpha", "proj_alpha_main")
    assert d_approve.allowed is False
    assert "strictly reserved for human operators" in d_approve.reason
    assert "RULE_AGENT_CONFINEMENT" in d_approve.matched_rules

    # Agent cannot publish
    d_publish = engine.evaluate("version:publish", agent_context, "org_alpha", "proj_alpha_main")
    assert d_publish.allowed is False
    assert "strictly reserved for human operators" in d_publish.reason
    assert "RULE_AGENT_CONFINEMENT" in d_publish.matched_rules


# -----------------------------------------------------------------------------
# 6. Negative Test: Deny-by-Default Without Database Manager
# -----------------------------------------------------------------------------

def test_deny_by_default_when_no_authoritative_store_configured():
    """PermissionEngine without db_manager denies all actions deterministically."""
    unbacked_engine = PermissionEngine(db_manager=None)

    context = SecurityContext(
        actor=Actor(actor_id="any_user", roles=["admin"], organization_id="org_any"),
        organization_id="org_any",
        project_id="proj_any",
    )

    decision = unbacked_engine.evaluate("run:create", context, "org_any", "proj_any")
    assert decision.allowed is False
    assert "not configured" in decision.reason
    assert "RULE_AUTH_STORE_UNAVAILABLE" in decision.matched_rules


# -----------------------------------------------------------------------------
# 7. Positive Test: Valid Authorized Access
# -----------------------------------------------------------------------------

def test_valid_authorized_admin_access(rbac_db):
    """Admin in DB has full rights across Core, Factory, Approvals, and Assignment."""
    engine = PermissionEngine(db_manager=rbac_db)

    admin_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            roles=[],  # Even if caller passes empty roles, DB gives admin!
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    # Admin actions allowed
    for action in [
        "run:create",
        "run:read",
        "run:cancel",
        "run:trace",
        "blueprint:create",
        "version:create",
        "version:approve",
        "version:publish",
        "agent:assign",
        "system:health",
        "system:capabilities",
    ]:
        decision = engine.evaluate(action, admin_context, "org_alpha", "proj_alpha_main")
        assert decision.allowed is True, f"Action {action} should be allowed for admin"


def test_valid_authorized_operator_access(rbac_db):
    """Operator in DB has execution, blueprint, and publish rights, but CANNOT approve."""
    engine = PermissionEngine(db_manager=rbac_db)

    op_context = SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            roles=[],  # Derived from DB
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )

    # Operator allowed actions
    for action in ["run:create", "run:read", "blueprint:create", "version:create", "version:publish", "agent:assign"]:
        decision = engine.evaluate(action, op_context, "org_alpha", "proj_alpha_main")
        assert decision.allowed is True, f"Action {action} should be allowed for operator"

    # Operator cannot approve
    decision_appr = engine.evaluate("version:approve", op_context, "org_alpha", "proj_alpha_main")
    assert decision_appr.allowed is False
    assert "is not permitted for actor 'user_alpha_op' with effective role 'operator'" in decision_appr.reason
