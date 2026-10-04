"""Unit tests for ARYN Core governance: Permissions, Budget, Audit."""

import pytest
from packages.contracts.core import (
    Actor,
    ActorType,
    AuditStatus,
    BudgetRule,
    SecurityContext,
)
from packages.contracts.runtime import RunUsage
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.usage.engine import BudgetEngine, BudgetExceededError
from modules.core.audit.logger import AuditLogger


from database.connection import DatabaseManager, create_db_engine
from database.schema import Base
from database.repositories.organization_repo import OrganizationRepository


def test_permission_engine_enforces_roles():
    engine_db = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine_db)
    db_manager = DatabaseManager(engine=engine_db)

    with db_manager.session() as s:
        org_repo = OrganizationRepository(s)
        org_repo.create_organization("org_test", "Test Org", "test-org")
        org_repo.add_member("org_test", "op_1", role="operator")
        org_repo.add_member("org_test", "vw_1", role="viewer")

        ctx_setup = SecurityContext(
            actor=Actor(actor_id="op_1", actor_type=ActorType.USER, organization_id="org_test"),
            organization_id="org_test",
            project_id="proj_test",
        ).sign()
        org_repo.create_project(ctx_setup, "proj_test", "Test Project", "test-proj")
        org_repo.add_project_member("proj_test", "op_1", role="operator")
        org_repo.add_project_member("proj_test", "vw_1", role="viewer")

    engine = PermissionEngine(db_manager=db_manager)
    actor_op = Actor(actor_id="op_1", actor_type=ActorType.USER, roles=["operator"], organization_id="org_test")
    context_op = SecurityContext(actor=actor_op, organization_id="org_test", project_id="proj_test").sign()

    # Operator can create run
    decision = engine.evaluate("run:create", context_op, "org_test", "proj_test")
    assert decision.allowed is True

    # Viewer cannot create run
    actor_viewer = Actor(actor_id="vw_1", actor_type=ActorType.USER, roles=["viewer"], organization_id="org_test")
    context_viewer = SecurityContext(actor=actor_viewer, organization_id="org_test", project_id="proj_test").sign()

    decision_viewer = engine.evaluate("run:create", context_viewer, "org_test", "proj_test")
    assert decision_viewer.allowed is False
    assert "is not permitted" in decision_viewer.reason

    with pytest.raises(PermissionDeniedError):
        engine.enforce("run:create", context_viewer, "org_test", "proj_test")


def test_permission_engine_enforces_tenant_isolation():
    engine_db = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine_db)
    db_manager = DatabaseManager(engine=engine_db)

    with db_manager.session() as s:
        org_repo = OrganizationRepository(s)
        org_repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
        org_repo.add_member("org_alpha", "adm_1", role="admin")

        ctx_alpha = SecurityContext(
            actor=Actor(actor_id="adm_1", actor_type=ActorType.USER, organization_id="org_alpha"),
            organization_id="org_alpha",
            project_id="proj_alpha",
        ).sign()
        org_repo.create_project(ctx_alpha, "proj_alpha", "Alpha Project", "alpha-proj")

        org_repo.create_organization("org_beta", "Beta Corp", "beta-corp")
        ctx_beta = SecurityContext(
            actor=Actor(actor_id="user_beta", actor_type=ActorType.USER, organization_id="org_beta"),
            organization_id="org_beta",
            project_id="proj_beta",
        ).sign()
        org_repo.create_project(ctx_beta, "proj_beta", "Beta Project", "beta-proj")

    engine = PermissionEngine(db_manager=db_manager)
    actor_admin = Actor(actor_id="adm_1", actor_type=ActorType.USER, roles=["admin"], organization_id="org_alpha")
    context_admin = SecurityContext(actor=actor_admin, organization_id="org_alpha", project_id="proj_alpha").sign()

    # Attempting to access org_beta
    decision = engine.evaluate("run:create", context_admin, "org_beta", "proj_beta")
    assert decision.allowed is False
    assert "Tenant boundary violation" in decision.reason


def test_budget_engine_preflight_and_accumulation():
    rule = BudgetRule(max_tokens_per_run=2000)
    engine = BudgetEngine(default_rule=rule)

    actor = Actor(actor_id="user_1", organization_id="org_1")
    context = SecurityContext(actor=actor, organization_id="org_1", project_id="proj_1")

    # Preflight OK
    engine.check_preflight(context, estimated_tokens=1500)

    # Preflight exceeded
    with pytest.raises(BudgetExceededError):
        engine.check_preflight(context, estimated_tokens=3000)

    # Usage recording
    engine.record_usage(context, RunUsage(input_tokens=100, output_tokens=50, total_tokens=150))
    engine.record_usage(context, RunUsage(input_tokens=200, output_tokens=100, total_tokens=300))
    assert engine.get_cumulative_tokens(context) == 450


def test_audit_logger_redacts_secrets_and_signs_events():
    logger = AuditLogger()
    actor = Actor(actor_id="user_sec", organization_id="org_sec")
    context = SecurityContext(actor=actor, organization_id="org_sec", project_id="proj_sec")

    sensitive_payload = {
        "user_query": "Please summarize financial report",
        "api_key": "sk-secret-token-1234567890",
        "nested": {
            "password": "SuperSecretPassword!",
            "auth_token": "Bearer abc123def456",
            "normal_data": 42,
        },
        "raw_header": "Authorization: Bearer secret_bearer_token",
    }

    event = logger.record(
        event_type="test.audit.sensitive",
        context=context,
        resource_id="res_audit_1",
        status=AuditStatus.ALLOWED,
        payload=sensitive_payload,
    )

    clean = event.redacted_payload
    assert clean["api_key"] == "[REDACTED]"
    assert clean["nested"]["password"] == "[REDACTED]"
    assert clean["nested"]["auth_token"] == "[REDACTED]"
    assert clean["nested"]["normal_data"] == 42
    assert "Bearer [REDACTED]" in clean["raw_header"]
    assert "secret_bearer_token" not in clean["raw_header"]

    # Verify SHA256 integrity reference is attached
    assert len(event.integrity_reference) == 64
    assert event.calculate_integrity() == event.integrity_reference
