"""Security, Isolation, Idempotency, and Recovery tests for ARYN Core and Persistence.

Covers:
1. Cross-tenant isolation and denial
2. Duplicate request / idempotency handling
3. Restart recovery of abandoned in-flight runs
4. Budget exhaustion preflight enforcement
5. Audit trail secret scrubbing in database records

Complies with ARYN-ARCH-001 Section 03 & 07 and ARYN-SEC-001.
"""

import pytest

from database.connection import DatabaseManager, create_db_engine
from database.schema import Base, AuditEventModel
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.run_state_repo import RunStateRepository
from database.repositories.budget_repo import BudgetRepository
from database.repositories.audit_repo import AuditRepository
from database.repositories.exceptions import TenantIsolationError

from packages.contracts.core import Actor, SecurityContext
from tests.conftest import bind_test_context
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeAdapter,
    RuntimeHealth,
    RuntimeCapabilities,
    RuntimeTrace,
)
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.usage.engine import BudgetExceededError


class DeterministicMockRuntimeAdapter(RuntimeAdapter):
    """Deterministic mock adapter for security and resilience testing."""

    async def model_availability(self, model, *, refresh=False):
        from packages.contracts.runtime import RuntimeModelAvailability
        return RuntimeModelAvailability(model=model, status="available", source="isolated-test")

    def __init__(self) -> None:
        self.invocations: int = 0
        self.last_request = None

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            is_healthy=True,
            status="healthy",
            platform="mock",
            version="1.0.0",
            listener_url="http://127.0.0.1:8642",
        )

    async def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            enabled_toolsets=[],
            available_toolsets=[],
            tools_confined=True,
        )

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        self.invocations += 1
        self.last_request = request
        return RunResult(
            run_id=f"run_mock_{self.invocations}",
            status=RunStatus.COMPLETED,
            output=f"Deterministic response for: {request.prompt}",
            usage=RunUsage(input_tokens=50, output_tokens=75, total_tokens=125),
            model=request.model,
            created_at=1700000000.0,
            completed_at=1700000001.0,
        )

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        self.invocations += 1
        self.last_request = request
        return f"run_async_{self.invocations}"

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        return RunResult(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            output="Async completed output",
            usage=RunUsage(input_tokens=100, output_tokens=100, total_tokens=200),
            model="mock-fast",
            created_at=1700000000.0,
            completed_at=1700000002.0,
        )

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        return True

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        return RuntimeTrace(run_id=run_id, events=[{"event": "completed"}])


@pytest.fixture
def test_db_manager():
    """Creates a shared SQLite database in memory with schema created."""
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return DatabaseManager(engine=engine)


@pytest.fixture
def seeded_db(test_db_manager):
    """Seeds test tenants, projects, and memberships into database."""
    with test_db_manager.session() as session:
        org_repo = OrganizationRepository(session)
        # Org Alpha
        org_repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
        org_repo.add_member("org_alpha", "user_alpha_admin", role="admin")
        org_repo.add_member("org_alpha", "user_alpha_viewer", role="viewer")

        ctx_alpha = SecurityContext(
            actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
            organization_id="org_alpha",
            project_id="proj_alpha_main",
        )
        org_repo.create_project(ctx_alpha, "proj_alpha_main", "Alpha Main", "alpha-main")

        # Org Beta
        org_repo.create_organization("org_beta", "Beta Corp", "beta-corp")
        org_repo.add_member("org_beta", "user_beta_admin", role="admin")

        ctx_beta = SecurityContext(
            actor=Actor(actor_id="user_beta_admin", organization_id="org_beta", roles=["admin"]),
            organization_id="org_beta",
            project_id="proj_beta_main",
        )
        org_repo.create_project(ctx_beta, "proj_beta_main", "Beta Main", "beta-main")

    return test_db_manager


# -----------------------------------------------------------------
# 1. Cross-Tenant Denial Tests
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_tenant_denial_on_run_execution(seeded_db):
    """Verifies that an actor from Org Alpha CANNOT execute or read in Org Beta."""
    adapter = DeterministicMockRuntimeAdapter()
    coordinator = RunCoordinator(runtime_adapter=adapter, db_manager=seeded_db)

    # Actor from Org Alpha trying to target Org Beta's project
    invalid_context = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",  # context org is alpha
        project_id="proj_beta_main",  # target project is in beta!
    ))

    _req = RunRequest(prompt="Hello", model="mock-deterministic")

    # Permission engine must reject due to tenant boundary validation
    with pytest.raises(PermissionDeniedError, match="Tenant boundary violation"):
        # Evaluating with target org as org_beta
        coordinator.permission_engine.enforce("run:create", invalid_context, target_org_id="org_beta", target_project_id="proj_beta_main")

    # In RunCoordinator, executing with mismatched context against foreign project in repository raises TenantIsolationError
    with seeded_db.session() as session:
        org_repo = OrganizationRepository(session)
        with pytest.raises(TenantIsolationError):
            org_repo.get_project(invalid_context, "proj_beta_main")


# -----------------------------------------------------------------
# 2. Idempotency / Duplicate Request Tests
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_request_idempotency_returns_cached_result(seeded_db):
    """Verifies that identical requests with same idempotency_key do not re-invoke runtime."""
    adapter = DeterministicMockRuntimeAdapter()
    coordinator = RunCoordinator(runtime_adapter=adapter, db_manager=seeded_db)

    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        correlation_id="corr_idempotent_01",
    ))

    req = RunRequest(
        prompt="Execute calculation #1",
        model="mock-fast",
        idempotency_key="idempotent_key_abc_123",
    )

    # First execution: runtime is invoked
    res1 = await coordinator.execute_managed_direct_turn(req, ctx)
    assert res1.status == RunStatus.COMPLETED
    assert adapter.invocations == 1
    first_run_id = res1.run_id

    # Second execution with EXACT SAME idempotency_key
    res2 = await coordinator.execute_managed_direct_turn(req, ctx)
    assert res2.status == RunStatus.COMPLETED
    # Runtime adapter invocation count MUST NOT increase
    assert adapter.invocations == 1
    # Run ID and output must match exactly
    assert res2.run_id == first_run_id
    assert res2.output == res1.output

    # Check audit events recorded
    with seeded_db.session() as session:
        audit_repo = AuditRepository(session)
        events = audit_repo.list_by_correlation(ctx, "corr_idempotent_01")
        event_types = [e.event_type for e in events]
        assert "core.run.idempotent_cached" in event_types


# -----------------------------------------------------------------
# 3. Restart Recovery Tests
# -----------------------------------------------------------------

def test_restart_recovery_transitions_in_flight_runs(seeded_db):
    """Verifies that abandoned in-flight runs are transitioned to 'failed' on restart."""
    adapter = DeterministicMockRuntimeAdapter()
    coordinator = RunCoordinator(runtime_adapter=adapter, db_manager=seeded_db)

    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
    ))

    # Seed 3 runs: 1 queued, 1 running, 1 already completed
    with seeded_db.session() as session:
        run_repo = RunStateRepository(session)
        run_repo.create_run(ctx, run_id="run_interrupted_1", prompt="p1", model="mock-model", provider="mock")
        # leaves it in 'queued'

        run_repo.create_run(ctx, run_id="run_interrupted_2", prompt="p2", model="mock-model", provider="mock")
        run_repo.transition_status(ctx, "run_interrupted_2", "started")
        run_repo.transition_status(ctx, "run_interrupted_2", "running")

        run_repo.create_run(ctx, run_id="run_normal_completed", prompt="p3", model="mock-model", provider="mock")
        run_repo.transition_status(ctx, "run_normal_completed", "started")
        run_repo.transition_status(ctx, "run_normal_completed", "running")
        run_repo.transition_status(ctx, "run_normal_completed", "completed", output="Finished")

    # Execute restart recovery
    recovered = coordinator.recover_in_flight_runs()
    assert len(recovered) == 2
    recovered_ids = {r["run_id"] for r in recovered}
    assert "run_interrupted_1" in recovered_ids
    assert "run_interrupted_2" in recovered_ids
    assert "run_normal_completed" not in recovered_ids

    # Verify run states in database
    with seeded_db.session() as session:
        run_repo = RunStateRepository(session)
        r1 = run_repo.get_run(ctx, "run_interrupted_1")
        assert r1.status == "outcome_unknown"
        assert "system restart / crash recovery" in r1.error_message

        r2 = run_repo.get_run(ctx, "run_interrupted_2")
        assert r2.status == "outcome_unknown"

        r3 = run_repo.get_run(ctx, "run_normal_completed")
        assert r3.status == "completed"

        # Verify no in-flight runs remain
        assert len(run_repo.list_in_flight_runs()) == 0


# -----------------------------------------------------------------
# 4. Budget Exhaustion Tests
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_budget_exhaustion_preflight_denial(seeded_db):
    """Verifies that requests exceeding project budget are rejected at preflight."""
    adapter = DeterministicMockRuntimeAdapter()
    coordinator = RunCoordinator(runtime_adapter=adapter, db_manager=seeded_db)

    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        correlation_id="corr_budget_exceeded_01",
    ))

    # Restrict budget to 256 tokens
    with seeded_db.session() as session:
        budget_repo = BudgetRepository(session)
        budget_repo.set_budget(ctx, max_tokens_per_run=256)

    # Default preflight estimate is 1000 tokens, which exceeds 256
    req = RunRequest(prompt="Heavy analytical task", model="mock-fast")

    with pytest.raises(BudgetExceededError, match="exceeds maximum allowed per run"):
        await coordinator.execute_managed_direct_turn(req, ctx)

    # Runtime adapter was NOT invoked
    assert adapter.invocations == 0

    # Audit event core.run.budget_exceeded was persisted in database
    with seeded_db.session() as session:
        audit_repo = AuditRepository(session)
        events = audit_repo.list_by_correlation(ctx, "corr_budget_exceeded_01")
        assert len(events) == 1
        assert events[0].event_type == "core.run.budget_exceeded"
        assert events[0].status == "denied"


# -----------------------------------------------------------------
# 5. Audit Secret Scrubbing in Database Storage
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_scrubs_secrets_before_persisting_to_db(seeded_db):
    """Verifies that secrets (API keys, Bearer tokens, passwords) are scrubbed before DB insert."""
    adapter = DeterministicMockRuntimeAdapter()
    coordinator = RunCoordinator(runtime_adapter=adapter, db_manager=seeded_db)

    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_alpha_main",
        correlation_id="corr_secret_test_01",
    ))

    raw_secret_key = "sk-ant-api03-TOP_SECRET_CREDENTIAL"
    raw_bearer = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitivePayload"
    raw_password = "SuperSecretPassword123"

    req = RunRequest(
        prompt="Process this query",
        model="mock-fast",
        metadata={
            "api_key": raw_secret_key,
            "auth_header": raw_bearer,
            "nested": {
                "password": raw_password,
                "public_info": "safe_data",
            },
        },
    )

    # Execute managed run
    result = await coordinator.execute_managed_direct_turn(req, ctx)
    assert result.status == RunStatus.COMPLETED

    # Query the raw database row for audit events
    with seeded_db.session() as session:
        events = session.query(AuditEventModel).filter_by(correlation_id="corr_secret_test_01").all()
        assert len(events) > 0

        for event in events:
            raw_payload_str = event.redacted_payload_json
            # Asserts raw secret strings DO NOT appear anywhere in the database text
            assert raw_secret_key not in raw_payload_str, f"Leaked API key in {event.event_type}"
            assert "eyJhbGci" not in raw_payload_str, f"Leaked Bearer token in {event.event_type}"
            assert raw_password not in raw_payload_str, f"Leaked password in {event.event_type}"
            # Verify redacted indicator is present if sensitive data was provided
            if "api_key" in raw_payload_str:
                assert '"api_key": "[REDACTED]"' in raw_payload_str
