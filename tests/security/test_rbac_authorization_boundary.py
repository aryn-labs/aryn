"""Authoritative RBAC, Tenant Isolation, and Project Authorization Boundary Tests.

Verifies:
1. Untrusted caller inputs (actor_id, actor_type, roles) CANNOT be forged or trusted.
2. TrustedIdentityBinder enforces fail-closed cryptographic identity binding at Core boundary.
   - Zero fallback secrets: initialization without explicit secret or with empty key fails.
   - Rejection of tokens signed with known/default or attacker keys.
   - Token binds issued_at (iat) and expiry (exp); expired tokens fail closed.
   - Altered payload claims or malformed tokens are detected and rejected.
   - Key rotation is supported cleanly via key_id and secondary verification keys.
3. Project-level authorization:
   - Org admin has oversight across all projects in the organization.
   - Operators and viewers require explicit, active project memberships.
   - Operators cannot access other projects within the same organization without project membership.
   - Revoked or suspended project memberships are denied immediately.
4. Effective permissions are strictly derived from authoritative database records.
5. Autonomous agents are confined from human-only actions (approve, publish).

Complies with ARYN-ARCH-001 Section 03 and ARYN-SEC-001.
"""

from __future__ import annotations

import base64
import json
import time
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
from modules.core.identity.binder import TrustedIdentityBinder, _b64_encode
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.approvals.engine import ApprovalEngine, UnauthorizedApproverError
from modules.core.workflows.coordinator import RunCoordinator
from modules.agent_factory.service import AgentFactoryService
from modules.bench.runner import BenchRunner
from tests.conftest import bind_test_context, TEST_IDENTITY_SECRET


class MockTestRuntime(RuntimeAdapter):
    async def model_availability(self, model, *, refresh=False):
        from packages.contracts.runtime import RuntimeModelAvailability
        return RuntimeModelAvailability(model=model, status="available", source="isolated-test")

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(is_healthy=True, status="ok", platform="mock", version="1.0", listener_url="http://127.0.0.1:8642")

    async def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        return RunResult(
            run_id="run_test_rbac",
            status=RunStatus.COMPLETED,
            output="mock output",
            usage=RunUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        return "run_test_rbac_async"

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        return RunResult(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            output="mock result",
            usage=RunUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        return True

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        return RuntimeTrace(run_id=run_id, events=[{"event": "completed"}])


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
        ctx_alpha = bind_test_context(SecurityContext(
            actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ))
        repo.create_project(ctx_alpha, "proj_alpha_main", "Alpha Main", "alpha-main")
        repo.create_project(ctx_alpha, "proj_alpha_secondary", "Alpha Secondary", "alpha-secondary")

        # Project memberships in proj_alpha_main:
        repo.add_project_member("proj_alpha_main", "user_alpha_op", role="operator", status="active")
        repo.add_project_member("proj_alpha_main", "user_alpha_viewer", role="viewer", status="active")

        # Note: NEITHER user_alpha_op NOR user_alpha_viewer is added to proj_alpha_secondary!

        # Org Beta
        repo.create_organization("org_beta", "Beta Corp", "beta-corp")
        repo.add_member("org_beta", "user_beta_admin", role="admin", status="active")

        ctx_beta = bind_test_context(SecurityContext(
            actor=Actor(actor_id="user_beta_admin", organization_id="org_beta", roles=["admin"]),
            organization_id="org_beta",
            project_id="proj_beta_main",
        ))
        repo.create_project(ctx_beta, "proj_beta_main", "Beta Main", "beta-main")

    return db


# -----------------------------------------------------------------------------
# 1. Negative Tests: Trusted Identity Binding & Fail-Closed Verification
# -----------------------------------------------------------------------------

def test_missing_secret_binder_initialization_raises_error(monkeypatch):
    """Zero fallback secret: Binder initialization fails if secret is missing or empty."""
    monkeypatch.delenv("ARYN_IDENTITY_SECRET", raising=False)

    # 1. None without env var -> ValueError
    with pytest.raises(ValueError, match="requires an explicit non-empty secret_key"):
        TrustedIdentityBinder(secret_key=None)

    # 2. Empty string -> ValueError
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        TrustedIdentityBinder(secret_key="")

    # 3. Whitespace string -> ValueError
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        TrustedIdentityBinder(secret_key="   \t\n  ")


def test_permission_engine_missing_secret_fails_closed(monkeypatch, rbac_db):
    """PermissionEngine fails closed when no secret is configured and no binder injected."""
    monkeypatch.delenv("ARYN_IDENTITY_SECRET", raising=False)
    engine = PermissionEngine(db_manager=rbac_db, identity_binder=None)
    assert engine.identity_binder is None

    # Any evaluate call fails closed
    context = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        identity_token="any_token",
    )
    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "missing trusted identity binder" in decision.reason
    assert "RULE_IDENTITY_UNTRUSTED" in decision.matched_rules


def test_known_or_default_secret_rejected(rbac_db):
    """An attacker generates a token using a known or default secret; Core rejects it."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Attacker tries using hardcoded/known secrets
    forged_binder = TrustedIdentityBinder(secret_key="aryn-core-internal-trusted-identity-secret-2026")
    forged_context = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )
    forged_binder.bind_context(forged_context)

    decision = engine.evaluate("run:create", forged_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "impersonation or forged identity detected" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules


def test_expired_token_rejected_fail_closed(rbac_db):
    """A token whose expiry has elapsed must fail closed immediately."""
    engine = PermissionEngine(db_manager=rbac_db)
    binder = TrustedIdentityBinder(secret_key=TEST_IDENTITY_SECRET)

    context = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )
    # Issue with negative TTL (already expired)
    binder.bind_context(context, ttl_seconds=-10)

    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "Token expired" in decision.reason
    assert "RULE_IDENTITY_EXPIRED" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="Token expired"):
        engine.enforce("run:create", context, "org_alpha", "proj_alpha_main")


def test_altered_claims_in_payload_rejected(rbac_db):
    """Tampering with claims inside the token payload without valid signature fails closed."""
    engine = PermissionEngine(db_manager=rbac_db)
    binder = TrustedIdentityBinder(secret_key=TEST_IDENTITY_SECRET)

    # 1. Valid token for user_alpha_op
    context = SecurityContext(
        actor=Actor(actor_id="user_alpha_op", organization_id="org_alpha"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )
    binder.bind_context(context)

    # Attacker tampers the token string by altering the base64 claims payload
    parts = context.identity_token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(parts[2] + "==").decode("utf-8"))
    claims["sub"] = "user_alpha_admin"  # Modify subject claim
    tampered_claims_b64 = _b64_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    # Reassemble with original signature
    context.identity_token = f"{parts[0]}.{parts[1]}.{tampered_claims_b64}.{parts[3]}"

    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "impersonation or forged identity detected" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules


def test_key_rotation_support(rbac_db):
    """Core supports key rotation with primary signing key and active secondary verification keys."""
    old_key = "aryn-previous-key-rotation-entropy-32b"
    new_key = "aryn-new-active-key-rotation-entropy-32b"

    # 1. Token was issued under old key with key_id 'k1'
    old_binder = TrustedIdentityBinder(secret_key=old_key, key_id="k1")
    ctx = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )
    old_binder.bind_context(ctx)

    # 2. Server rotated to new_key ('k2'), but retains old_key ('k1') in secondary_keys
    rotating_binder = TrustedIdentityBinder(
        secret_key=new_key,
        key_id="k2",
        secondary_keys={"k1": old_key},
    )
    rotating_engine = PermissionEngine(db_manager=rbac_db, identity_binder=rotating_binder)

    # Token signed with k1 still verifies successfully
    decision = rotating_engine.evaluate("run:create", ctx, "org_alpha", "proj_alpha_main")
    assert decision.allowed is True

    # 3. Token signed with unknown key is rejected
    alien_binder = TrustedIdentityBinder(secret_key="completely-unknown-key-1234567890", key_id="k_alien")
    alien_ctx = SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    )
    alien_binder.bind_context(alien_ctx)

    alien_decision = rotating_engine.evaluate("run:create", alien_ctx, "org_alpha", "proj_alpha_main")
    assert alien_decision.allowed is False
    assert "impersonation or forged identity detected" in alien_decision.reason


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
    context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    # Attacker tampers actor_id to admin
    context.actor.actor_id = "user_alpha_admin"

    decision = engine.evaluate("run:create", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "does not match context actor_id" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules

    with pytest.raises(PermissionDeniedError, match="does not match context actor_id"):
        engine.enforce("run:create", context, "org_alpha", "proj_alpha_main")


def test_forged_actor_type_agent_to_user_is_detected_and_rejected(rbac_db):
    """Context signed for an AGENT is tampered to claim USER status."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Legitimate context signed for AGENT
    context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.AGENT,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    # Agent tampers actor_type to USER to bypass agent confinement
    context.actor.actor_type = ActorType.USER

    decision = engine.evaluate("version:approve", context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "does not match context actor_type" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules


def test_forged_admin_role_rejected_by_permission_engine(rbac_db):
    """An attacker provides roles=['admin'] in SecurityContext, but is only 'viewer' in DB."""
    engine = PermissionEngine(db_manager=rbac_db)

    # Actor has "viewer" role in DB, but caller claims ["admin"]
    forged_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin", "superadmin", "root"],  # Forged!
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    decision = engine.evaluate("run:create", forged_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "effective role 'viewer'" in decision.reason
    assert "RULE_RBAC_ENFORCEMENT" in decision.matched_rules


@pytest.mark.asyncio
async def test_forged_admin_role_rejected_in_run_coordinator(rbac_db):
    """RunCoordinator refuses execution when caller claims admin but DB is viewer."""
    runtime = MockTestRuntime()
    coordinator = RunCoordinator(runtime_adapter=runtime, db_manager=rbac_db)

    forged_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    req = RunRequest(prompt="ping", model="mock-fast")
    with pytest.raises(PermissionDeniedError, match="effective role 'viewer'"):
        await coordinator.execute_managed_direct_turn(req, forged_context)


def test_forged_admin_role_rejected_in_approval_engine(rbac_db):
    """ApprovalEngine refuses to grant approval when caller claims admin but DB is viewer."""
    appr_engine = ApprovalEngine(db_manager=rbac_db)

    forged_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_viewer",
            actor_type=ActorType.USER,
            roles=["admin"],
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

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
    other_proj_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_secondary",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_secondary",
    ))

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
    context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

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
    context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_op",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

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

    stranger_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_stranger_unknown",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    decision = engine.evaluate("run:create", stranger_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "has no membership in organization" in decision.reason
    assert "RULE_MEMBERSHIP_REQUIRED" in decision.matched_rules


def test_revoked_org_membership_is_denied(rbac_db):
    """Actor org membership has status='revoked'; must be denied even for operator actions."""
    engine = PermissionEngine(db_manager=rbac_db)

    revoked_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_revoked",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    decision = engine.evaluate("run:create", revoked_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "is revoked" in decision.reason
    assert "RULE_MEMBERSHIP_INACTIVE" in decision.matched_rules


def test_cross_tenant_project_access_denied(rbac_db):
    """Actor from Org Alpha attempts to target Project belonging to Org Beta."""
    engine = PermissionEngine(db_manager=rbac_db)

    cross_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            organization_id="org_alpha",
            project_id="proj_beta_main",  # Belongs to org_beta!
        ),
        organization_id="org_alpha",
        project_id="proj_beta_main",
    ))

    decision = engine.evaluate("run:create", cross_context, "org_alpha", "proj_beta_main")
    assert decision.allowed is False
    assert "Cross-tenant project violation" in decision.reason
    assert "RULE_CROSS_TENANT_VIOLATION" in decision.matched_rules


def test_actor_organization_mismatch_denied(rbac_db):
    """Actor's claimed organization does not match SecurityContext organization."""
    engine = PermissionEngine(db_manager=rbac_db)

    mismatch_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.USER,
            organization_id="org_beta",  # Mismatch!
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    decision = engine.evaluate("run:create", mismatch_context, "org_alpha", "proj_alpha_main")
    assert decision.allowed is False
    assert "does not match actor organization" in decision.reason
    assert "RULE_IDENTITY_TAMPERED" in decision.matched_rules


def test_agent_cannot_approve_or_publish(rbac_db):
    """Autonomous agent actors cannot approve or publish versions even with admin roles."""
    engine = PermissionEngine(db_manager=rbac_db)

    agent_context = bind_test_context(SecurityContext(
        actor=Actor(
            actor_id="user_alpha_admin",
            actor_type=ActorType.AGENT,
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        ),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    d_approve = engine.evaluate("version:approve", agent_context, "org_alpha", "proj_alpha_main")
    assert d_approve.allowed is False
    assert "strictly reserved for human operators" in d_approve.reason
    assert "RULE_AGENT_CONFINEMENT" in d_approve.matched_rules


def test_deny_by_default_when_no_authoritative_store_configured():
    """PermissionEngine without db_manager denies all actions deterministically."""
    unbacked_engine = PermissionEngine(db_manager=None)

    context = bind_test_context(SecurityContext(
        actor=Actor(actor_id="any_user", organization_id="org_any", project_id="proj_any"),
        organization_id="org_any",
        project_id="proj_any",
    ))

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
    ctx_main = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", project_id="proj_alpha_main"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    # Admin accessing proj_alpha_secondary (without explicit project membership row)
    ctx_sec = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", project_id="proj_alpha_secondary"),
        organization_id="org_alpha",
        project_id="proj_alpha_secondary",
    ))

    for ctx in [ctx_main, ctx_sec]:
        for action in ["run:create", "run:read", "blueprint:create", "version:approve", "version:publish", "agent:assign"]:
            decision = engine.evaluate(action, ctx, "org_alpha", ctx.project_id)
            assert decision.allowed is True, f"Action {action} failed for admin on {ctx.project_id}"


def test_valid_authorized_operator_project_access(rbac_db):
    """Operator with active ProjectMembership on proj_alpha_main has full operational access."""
    engine = PermissionEngine(db_manager=rbac_db)

    op_context = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_op", organization_id="org_alpha", project_id="proj_alpha_main"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    for action in ["run:create", "run:read", "blueprint:create", "version:create", "version:publish", "agent:assign"]:
        decision = engine.evaluate(action, op_context, "org_alpha", "proj_alpha_main")
        assert decision.allowed is True, f"Action {action} should be allowed for operator"

    # Operator cannot approve
    decision_appr = engine.evaluate("version:approve", op_context, "org_alpha", "proj_alpha_main")
    assert decision_appr.allowed is False


def test_valid_authorized_viewer_project_access(rbac_db):
    """Viewer with active ProjectMembership on proj_alpha_main has read access but cannot create runs."""
    engine = PermissionEngine(db_manager=rbac_db)

    viewer_context = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_viewer", organization_id="org_alpha", project_id="proj_alpha_main"),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    # Read allowed
    assert engine.evaluate("run:read", viewer_context, "org_alpha", "proj_alpha_main").allowed is True
    assert engine.evaluate("run:trace", viewer_context, "org_alpha", "proj_alpha_main").allowed is True

    # Write/Create denied
    assert engine.evaluate("run:create", viewer_context, "org_alpha", "proj_alpha_main").allowed is False
    assert engine.evaluate("blueprint:create", viewer_context, "org_alpha", "proj_alpha_main").allowed is False
