"""Unit tests for ARYN Core database repository layer.

Tests OrganizationRepository, RunStateRepository, AuditRepository, and BudgetRepository.
Verifies SQLite local persistence, deterministic state machine, and tenant isolation.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import create_db_engine, init_db
from database.schema import Base
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.run_state_repo import RunStateRepository
from database.repositories.audit_repo import AuditRepository
from database.repositories.budget_repo import BudgetRepository
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    TenantIsolationError,
)
from packages.contracts.core import (
    Actor,
    ActorType,
    AuditEvent,
    AuditStatus,
    BudgetRule,
    SecurityContext,
)
from packages.contracts.runtime import RunUsage
from modules.core.usage.engine import BudgetExceededError


@pytest.fixture
def db_session():
    """Provides an isolated in-memory SQLite database session for each test."""
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def security_context():
    actor = Actor(
        actor_id="user_test_01",
        actor_type=ActorType.USER,
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        roles=["admin"],
    )
    return SecurityContext(
        actor=actor,
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        correlation_id="corr_test_001",
    )


# ---------------------------------------------------------
# OrganizationRepository Tests
# ---------------------------------------------------------

def test_organization_repo_crud_and_duplicates(db_session, security_context):
    repo = OrganizationRepository(db_session)
    org = repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
    assert org.id == "org_alpha"
    assert org.name == "Alpha Corp"

    # Duplicate org rejection
    with pytest.raises(DuplicateEntityError):
        repo.create_organization("org_alpha", "Alpha Again", "alpha-dup")

    # Add member
    member = repo.add_member("org_alpha", "user_test_01", "admin")
    assert member.role == "admin"

    # Duplicate member rejection
    with pytest.raises(DuplicateEntityError):
        repo.add_member("org_alpha", "user_test_01", "operator")

    # Create and list projects
    proj = repo.create_project(security_context, "proj_alpha_main", "Main Project", "main")
    assert proj.id == "proj_alpha_main"

    projects = repo.list_projects(security_context)
    assert len(projects) == 1
    assert projects[0].id == "proj_alpha_main"


def test_organization_repo_tenant_isolation(db_session, security_context):
    repo = OrganizationRepository(db_session)
    repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
    repo.create_organization("org_beta", "Beta Corp", "beta-corp")

    beta_ctx = SecurityContext(
        actor=Actor(actor_id="user_beta", organization_id="org_beta", roles=["admin"]),
        organization_id="org_beta",
        project_id="proj_beta_main",
    )
    repo.create_project(beta_ctx, "proj_beta_main", "Beta Main", "main")

    # Cross-tenant project access rejection
    with pytest.raises(TenantIsolationError):
        repo.get_project(security_context, "proj_beta_main")


# ---------------------------------------------------------
# RunStateRepository Tests
# ---------------------------------------------------------

def test_run_state_repo_lifecycle_and_state_machine(db_session, security_context):
    org_repo = OrganizationRepository(db_session)
    org_repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
    org_repo.create_project(security_context, "proj_alpha_main", "Main", "main")

    run_repo = RunStateRepository(db_session)
    run = run_repo.create_run(
        context=security_context,
        run_id="run_001",
        prompt="Explain quantum entanglement",
        model="stealth/space-bunny-alpha",
        provider="nous",
        idempotency_key="idem_001",
    )
    assert run.status == "queued"

    # Valid transitions: queued -> started -> running -> completed
    run_started = run_repo.transition_status(security_context, "run_001", "started")
    assert run_started.status == "started"

    run_running = run_repo.transition_status(security_context, "run_001", "running")
    assert run_running.status == "running"

    usage = RunUsage(input_tokens=100, output_tokens=150, total_tokens=250)
    run_completed = run_repo.transition_status(
        security_context,
        "run_001",
        "completed",
        output="Quantum entanglement is a physical phenomenon...",
        usage=usage,
    )
    assert run_completed.status == "completed"
    assert run_completed.completed_at is not None
    assert run_completed.total_tokens == 250

    # Illegal transition: completed (terminal) -> running must raise InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        run_repo.transition_status(security_context, "run_001", "running")


def test_run_state_repo_invalid_transitions(db_session, security_context):
    org_repo = OrganizationRepository(db_session)
    org_repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
    org_repo.create_project(security_context, "proj_alpha_main", "Main", "main")

    run_repo = RunStateRepository(db_session)
    run_repo.create_run(
        context=security_context,
        run_id="run_002",
        prompt="Test invalid transition",
        model="test-model",
        provider="mock",
    )

    # Cannot skip straight from queued to completed
    with pytest.raises(InvalidStateTransitionError):
        run_repo.transition_status(security_context, "run_002", "completed")

    # queued -> failed is allowed
    failed = run_repo.transition_status(security_context, "run_002", "failed", error_message="Fatal crash")
    assert failed.status == "failed"

    # failed is terminal; cannot transition to started
    with pytest.raises(InvalidStateTransitionError):
        run_repo.transition_status(security_context, "run_002", "started")


def test_run_state_repo_idempotency_and_tenant_isolation(db_session, security_context):
    org_repo = OrganizationRepository(db_session)
    org_repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
    org_repo.create_project(security_context, "proj_alpha_main", "Main", "main")

    run_repo = RunStateRepository(db_session)
    run_repo.create_run(
        context=security_context,
        run_id="run_idem_test",
        prompt="Prompt test",
        model="test-model",
        provider="mock",
        idempotency_key="unique_key_42",
    )

    found = run_repo.get_run_by_idempotency_key(security_context, "unique_key_42")
    assert found is not None
    assert found.id == "run_idem_test"

    # Cross-tenant context cannot access the run
    foreign_ctx = SecurityContext(
        actor=Actor(actor_id="user_beta", organization_id="org_beta", roles=["admin"]),
        organization_id="org_beta",
        project_id="proj_beta_main",
    )
    with pytest.raises(TenantIsolationError):
        run_repo.get_run(foreign_ctx, "run_idem_test")


# ---------------------------------------------------------
# AuditRepository Tests
# ---------------------------------------------------------

def test_audit_repo_records_and_retrieves_events(db_session, security_context):
    repo = AuditRepository(db_session)

    evt = AuditEvent(
        event_id="evt_test_001",
        event_type="core.run.initiated",
        organization_id=security_context.organization_id,
        project_id=security_context.project_id,
        actor_type=security_context.actor.actor_type.value,
        actor_id=security_context.actor.actor_id,
        correlation_id=security_context.correlation_id,
        resource_id="run_001",
        status=AuditStatus.ALLOWED,
        redacted_payload={"model": "test-model", "clean_key": "safe_value"},
    )
    evt.integrity_reference = evt.calculate_integrity()

    saved = repo.record_event(evt)
    assert saved.event_id == "evt_test_001"
    assert saved.integrity_reference == evt.integrity_reference

    # Retrieve by correlation ID
    events = repo.list_by_correlation(security_context, security_context.correlation_id)
    assert len(events) == 1
    assert events[0].event_id == "evt_test_001"

    # Duplicate rejection
    with pytest.raises(DuplicateEntityError):
        repo.record_event(evt)

    # Cross-tenant audit boundary check
    foreign_ctx = SecurityContext(
        actor=Actor(actor_id="user_beta", organization_id="org_beta", roles=["admin"]),
        organization_id="org_beta",
        project_id="proj_beta_main",
    )
    with pytest.raises(TenantIsolationError):
        repo.get_event(foreign_ctx, "evt_test_001")


# ---------------------------------------------------------
# BudgetRepository Tests
# ---------------------------------------------------------

def test_budget_repo_lifecycle_and_preflight(db_session, security_context):
    repo = BudgetRepository(db_session)

    budget = repo.set_budget(
        context=security_context,
        max_tokens_per_run=2048,
        max_turns=5,
        max_cost_usd=0.25,
    )
    assert budget.max_tokens_per_run == 2048
    assert budget.cumulative_tokens == 0

    # Preflight check within budget: should not raise
    repo.check_preflight(security_context, estimated_tokens=1000)

    # Preflight check exceeding budget: must raise BudgetExceededError
    with pytest.raises(BudgetExceededError):
        repo.check_preflight(security_context, estimated_tokens=3000)

    # Record usage
    updated = repo.record_usage(security_context, tokens=500, cost_usd=0.01)
    assert updated.cumulative_tokens == 500
    assert updated.cumulative_cost_usd == 0.01

    updated2 = repo.record_usage(security_context, tokens=600, cost_usd=0.02)
    assert updated2.cumulative_tokens == 1100
