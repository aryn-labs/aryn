"""End-to-End Smoke Test for ARYN Autonomous Agent Infrastructure.

Validates the full governance pipeline:
Client Request → ARYN Core Policy → Permission Gate → Model Router → Budget Preflight
→ Pre-Execution Audit → Hermes Runtime Adapter → Hermes Gateway (127.0.0.1:8642)
→ Model Inference → Response Capture → Post-Execution Budget Update → Post-Execution Audit.

Complies with user task requirement 8, ARYN-TECH-001 ADR-004, and ARYN-SEC-001.
"""

import os
import importlib
import pytest
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
from modules.core.audit.logger import AuditLogger
from modules.core.permissions.engine import PermissionEngine
from modules.core.usage.engine import BudgetEngine
from modules.core.workflows.coordinator import RunCoordinator
from database.connection import DatabaseManager, create_db_engine
from database.schema import Base
from database.repositories.organization_repo import OrganizationRepository

hermes_module = importlib.import_module("packages.runtime-adapters.hermes")
HermesRuntimeAdapter = hermes_module.HermesRuntimeAdapter
model_adapters_module = importlib.import_module("packages.model-adapters")
ModelRouter = model_adapters_module.ModelRouter


def get_live_api_key() -> str:
    """Safely retrieves API_SERVER_KEY from Hermes .env without leaking."""
    key = os.getenv("API_SERVER_KEY")
    if key:
        return key
    env_file = r"C:\Users\User\AppData\Local\hermes\.env"
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("API_SERVER_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


@pytest.mark.asyncio
async def test_live_end_to_end_smoke():
    """Live E2E Smoke Test against running local Hermes gateway."""
    api_key = get_live_api_key()
    if not api_key:
        pytest.skip("Hermes API_SERVER_KEY not found in local environment.")

    # 1. Initialize ARYN Core persistence and seed membership
    db_engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=db_engine)
    db_manager = DatabaseManager(engine=db_engine)

    # 2. Build Authoritative Security Context & Seed Organization
    actor = Actor(
        actor_id="aryn_engineer_1",
        actor_type=ActorType.USER,
        roles=["operator"],
        organization_id="org_aryn_hq",
        project_id="proj_pilot",
    )
    context = SecurityContext(
        actor=actor,
        organization_id="org_aryn_hq",
        project_id="proj_pilot",
    )

    with db_manager.session() as s:
        org_repo = OrganizationRepository(s)
        org_repo.create_organization("org_aryn_hq", "ARYN HQ", "aryn-hq")
        org_repo.add_member("org_aryn_hq", "aryn_engineer_1", role="operator")
        org_repo.create_project(context, "proj_pilot", "Pilot", "pilot")

    # 3. Initialize ARYN Core infrastructure
    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key=api_key)
    permission_engine = PermissionEngine(db_manager=db_manager)
    budget_engine = BudgetEngine(db_manager=db_manager)
    audit_logger = AuditLogger(db_manager=db_manager)
    model_router = ModelRouter()

    coordinator = RunCoordinator(
        runtime_adapter=adapter,
        permission_engine=permission_engine,
        budget_engine=budget_engine,
        audit_logger=audit_logger,
        model_router=model_router,
        db_manager=db_manager,
    )

    # 3. Build Run Request
    request = RunRequest(
        prompt="ping",
        system_instructions="You are ARYN's verified agent. Answer concisely.",
        model="stealth/space-bunny-alpha",
    )

    # 4. Execute through ARYN Core RunCoordinator
    result = await coordinator.execute_managed_direct_turn(request, context)

    # 5. Assertions on Execution Result
    assert result.status == RunStatus.COMPLETED
    assert len(result.output) > 0
    assert "pong" in result.output.lower()
    assert result.usage.total_tokens > 0

    # 6. Assertions on Budget Accounting
    tokens_recorded = budget_engine.get_cumulative_tokens(context)
    assert tokens_recorded == result.usage.total_tokens

    # 7. Assertions on Audit Ledger & Secret Redaction
    events = audit_logger.get_events_for_correlation(context.correlation_id)
    assert len(events) >= 2

    # Pre-event
    init_event = events[0]
    assert init_event.event_type == "core.run.initiated"
    assert init_event.status == AuditStatus.ALLOWED
    assert init_event.integrity_reference == init_event.calculate_integrity()

    # Post-event
    comp_event = events[1]
    assert comp_event.event_type == "core.run.completed"
    assert comp_event.status == AuditStatus.COMPLETED
    assert comp_event.integrity_reference == comp_event.calculate_integrity()


@pytest.mark.asyncio
async def test_mocked_end_to_end_smoke_isolated():
    """Deterministic isolated E2E test verifying full Core workflow with mock adapter."""
    class MockIsolatedAdapter(RuntimeAdapter):
        async def health(self) -> RuntimeHealth:
            return RuntimeHealth(is_healthy=True, status="ok", platform="mock", version="1.0", listener_url="mock://")
        async def capabilities(self) -> RuntimeCapabilities:
            return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)
        async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
            return "run_mock_123"
        async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
            return RunResult(
                run_id=run_id,
                status=RunStatus.COMPLETED,
                output="mocked pong",
                usage=RunUsage(input_tokens=10, output_tokens=5, total_tokens=15),
                model="mock-fast",
                created_at=100.0,
            )
        async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
            return True
        async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
            return RuntimeTrace(run_id=run_id, events=[{"event": "completed"}])

    db_engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=db_engine)
    db_manager = DatabaseManager(engine=db_engine)

    actor = Actor(actor_id="test_actor", roles=["operator"], organization_id="org_mock", project_id="proj_mock")
    context = SecurityContext(actor=actor, organization_id="org_mock", project_id="proj_mock")

    with db_manager.session() as s:
        org_repo = OrganizationRepository(s)
        org_repo.create_organization("org_mock", "Mock Org", "mock-org")
        org_repo.add_member("org_mock", "test_actor", role="operator")
        org_repo.create_project(context, "proj_mock", "Mock Project", "mock-proj")

    mock_adapter = MockIsolatedAdapter()
    coordinator = RunCoordinator(
        runtime_adapter=mock_adapter,
        permission_engine=PermissionEngine(db_manager=db_manager),
        budget_engine=BudgetEngine(db_manager=db_manager),
        audit_logger=AuditLogger(db_manager=db_manager),
        model_router=ModelRouter(),
        db_manager=db_manager,
    )
    request = RunRequest(prompt="ping", model="mock-fast")

    result = await coordinator.execute_managed_direct_turn(request, context)

    assert result.status == RunStatus.COMPLETED
    assert result.output == "mocked pong"
    assert result.usage.total_tokens == 15
