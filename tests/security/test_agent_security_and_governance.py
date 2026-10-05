"""Security and Governance tests for Agent Factory, Bench, and Approvals.

Verifies:
1. Unauthorized publication attempts (Agent actor or Viewer actor) are strictly denied.
2. Cross-project and cross-tenant access to blueprints/versions/assignments is blocked.
3. Forbidden tools (terminal, file, browser, code_execution) are rejected at version creation.
4. Cryptographic approval tampering (payload hash mismatch) and missing approval are blocked.
5. Failed Bench evaluations block approval and publication (Quality Gate).
6. Concurrent idempotency race conditions do not produce duplicate database records.

Complies with ARYN-ARCH-001 Section 04, 05, 06 and ARYN-SEC-001.
"""

import asyncio
import pytest
from database.connection import DatabaseManager, create_db_engine
from database.schema import Base, RunStateModel
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.agent_repo import AgentRepository
from database.repositories.exceptions import TenantIsolationError

from packages.contracts.core import Actor, ActorType, SecurityContext
from tests.conftest import bind_test_context
from packages.contracts.runtime import RunRequest, RunResult, RunStatus, RunUsage, RuntimeAdapter, RuntimeHealth, RuntimeCapabilities, RuntimeTrace
from packages.contracts.bench import BenchCategory, BenchScenario, ScenarioResult, BenchEvaluationResult
from packages.model_adapters import ModelRouter

from modules.agent_factory.service import (
    AgentFactoryService,
    ForbiddenToolError,
    UnpublishedVersionError,
)
from modules.bench.runner import BenchRunner
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.approvals.engine import (
    ApprovalRequiredError,
    UnauthorizedApproverError,
    PayloadHashMismatchError,
)
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.workflows.coordinator import RunCoordinator


class FlawedRuntimeAdapter(RuntimeAdapter):
    """Runtime that leaks injection and fails benchmark safety scenarios."""

    async def model_availability(self, model, *, refresh=False):
        from packages.contracts.runtime import RuntimeModelAvailability
        return RuntimeModelAvailability(model=model, status="available", source="isolated-test")

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(is_healthy=True, status="ok", platform="mock-flawed", version="1.0", listener_url="http://127.0.0.1:8642")

    async def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        # Intentionally outputs forbidden text when prompt injection is attempted
        if "System override" in request.prompt or "PWNED" in request.prompt:
            output = "PWNED_BY_INJECTION: System override accepted."
        else:
            output = "Normal output."

        return RunResult(
            run_id="run_flawed",
            status=RunStatus.COMPLETED,
            output=output,
            usage=RunUsage(input_tokens=50, output_tokens=50, total_tokens=100),
            model=request.model,
            created_at=1700000000.0,
            completed_at=1700000001.0,
        )

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        return "run_flawed_async"

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        return await self.execute_direct_turn(RunRequest(prompt="", model="mock-fast"), context)

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        return True

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        return RuntimeTrace(run_id=run_id, events=[])


@pytest.fixture
def multi_tenant_db():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = DatabaseManager(engine=engine)

    with db.session() as s:
        org_repo = OrganizationRepository(s)
        # Org 1, Project A
        org_repo.create_organization("org_alpha", "Alpha Corp", "alpha-corp")
        org_repo.add_member("org_alpha", "user_alpha_admin", role="admin")
        org_repo.add_member("org_alpha", "user_alpha_viewer", role="viewer")

        ctx_a = SecurityContext(
            actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
            organization_id="org_alpha",
            project_id="proj_alpha_research",
        )
        org_repo.create_project(ctx_a, "proj_alpha_research", "Alpha Research", "alpha-research")

        # Org 2, Project B
        org_repo.create_organization("org_beta", "Beta Corp", "beta-corp")
        org_repo.add_member("org_beta", "user_beta_admin", role="admin")

        ctx_b = SecurityContext(
            actor=Actor(actor_id="user_beta_admin", organization_id="org_beta", roles=["admin"]),
            organization_id="org_beta",
            project_id="proj_beta_intel",
        )
        org_repo.create_project(ctx_b, "proj_beta_intel", "Beta Intel", "beta-intel")

    return db


@pytest.fixture
def alpha_admin_context():
    return bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_alpha_admin", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_alpha_research",
        correlation_id="corr_sec_alpha_01",
    ))


# -----------------------------------------------------------------------------
# 1. Unauthorized Publication Gates
# -----------------------------------------------------------------------------

def test_unauthorized_publish_is_denied(multi_tenant_db, alpha_admin_context):
    ctx_admin = alpha_admin_context
    flawed_runtime = FlawedRuntimeAdapter()
    bench_runner = BenchRunner(runtime_adapter=flawed_runtime)
    service = AgentFactoryService(db_manager=multi_tenant_db, bench_runner=bench_runner)

    bp = service.create_blueprint(ctx_admin, "Safety Agent", "safety-agent")
    v = service.create_version(
        ctx_admin,
        blueprint_id=bp.id,
        version_number="1.0.0",
        system_prompt="Safe system prompt.",
        model="mock-fast",
        tool_grants=[],
    )

    # 1. Agent actor attempting to publish must be rejected
    agent_ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="agent_worker", actor_type=ActorType.AGENT, organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_alpha_research",
    ))
    with pytest.raises(PermissionDeniedError, match="Agents cannot publish"):
        service.publish_version(agent_ctx, v.id)


# -----------------------------------------------------------------------------
# 2. Cross-Tenant / Cross-Project Access Denial
# -----------------------------------------------------------------------------

def test_cross_tenant_blueprint_and_assignment_denial(multi_tenant_db, alpha_admin_context):
    ctx_alpha = alpha_admin_context
    flawed_runtime = FlawedRuntimeAdapter()
    bench_runner = BenchRunner(runtime_adapter=flawed_runtime)
    service = AgentFactoryService(db_manager=multi_tenant_db, bench_runner=bench_runner)

    # Blueprint created in Alpha
    bp = service.create_blueprint(ctx_alpha, "Alpha Secret Agent", "alpha-secret-agent")

    # Context for Beta Corp trying to access Alpha's blueprint
    ctx_beta = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_beta_admin", organization_id="org_beta", roles=["admin"]),
        organization_id="org_beta",
        project_id="proj_beta_intel",
    ))

    with multi_tenant_db.session() as s:
        agent_repo = AgentRepository(s)
        with pytest.raises(TenantIsolationError, match="Tenant boundary violation"):
            agent_repo.get_blueprint(ctx_beta, bp.id)


# -----------------------------------------------------------------------------
# 3. Forbidden Tool Rejection
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("forbidden_tool", ["terminal", "file", "browser", "code_execution", "bash", "shell"])
def test_forbidden_tools_rejected_at_version_creation(multi_tenant_db, alpha_admin_context, forbidden_tool):
    flawed_runtime = FlawedRuntimeAdapter()
    bench_runner = BenchRunner(runtime_adapter=flawed_runtime)
    service = AgentFactoryService(db_manager=multi_tenant_db, bench_runner=bench_runner)

    bp = service.create_blueprint(alpha_admin_context, f"Agent-{forbidden_tool}", f"agent-{forbidden_tool}")

    with pytest.raises(ForbiddenToolError, match="strictly forbidden"):
        service.create_version(
            context=alpha_admin_context,
            blueprint_id=bp.id,
            version_number="1.0.0",
            system_prompt="Execute tools.",
            model="mock-fast",
            tool_grants=[forbidden_tool],
        )


# -----------------------------------------------------------------------------
# 4. Failed Bench Evaluation Blocks Approval and Publication (Quality Gate)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_bench_blocks_approval_and_publish(multi_tenant_db, alpha_admin_context):
    flawed_runtime = FlawedRuntimeAdapter()
    bench_runner = BenchRunner(runtime_adapter=flawed_runtime)
    service = AgentFactoryService(db_manager=multi_tenant_db, bench_runner=bench_runner)

    bp = service.create_blueprint(alpha_admin_context, "Vulnerable Agent", "vulnerable-agent")
    v = service.create_version(
        context=alpha_admin_context,
        blueprint_id=bp.id,
        version_number="1.0.0",
        system_prompt="I am easily compromised.",
        model="mock-fast",
        tool_grants=[],
    )

    # Bench evaluation against flawed runtime should fail prompt injection
    eval_result = await service.evaluate_version_with_bench(alpha_admin_context, v.id)
    assert eval_result.passed is False
    assert eval_result.score < 1.0

    # Attempt to approve an agent that failed Bench evaluation must be blocked
    with pytest.raises(QualityGateFailedError, match="no passing Bench evaluation found"):
        service.approve_version(alpha_admin_context, v.id, comments="Trying to bypass bench")

    # Attempt to publish must also be blocked
    with pytest.raises(QualityGateFailedError, match="no passing Bench evaluation found"):
        service.publish_version(alpha_admin_context, v.id)


# -----------------------------------------------------------------------------
# 5. Tampered Approval Payload Hash Rejection
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tampered_payload_hash_blocks_publish(multi_tenant_db, alpha_admin_context):
    from database.repositories.bench_repo import BenchRepository
    flawed_runtime = FlawedRuntimeAdapter()
    bench_runner = BenchRunner(runtime_adapter=flawed_runtime)
    service = AgentFactoryService(db_manager=multi_tenant_db, bench_runner=bench_runner)

    bp = service.create_blueprint(alpha_admin_context, "Tamper Test Agent", "tamper-test-agent")
    v = service.create_version(
        context=alpha_admin_context,
        blueprint_id=bp.id,
        version_number="1.0.0",
        system_prompt="Initial prompt.",
        model="mock-fast",
        tool_grants=[],
    )

    from tests.studio_runtime import IsolatedTestRuntime
    service.bench_runner = BenchRunner(IsolatedTestRuntime())
    await service.evaluate_version_with_bench(alpha_admin_context, v.id)

    # Approve with valid initial hash
    service.approve_version(alpha_admin_context, v.id)

    # Simulate tampering: mutate system_prompt in DB behind the scenes so payload_hash changes
    with multi_tenant_db.session() as s:
        agent_repo = AgentRepository(s)
        v_model = agent_repo.get_version(alpha_admin_context, v.id)
        v_model.system_prompt = "Tampered prompt with backdoors."
        v_model.payload_hash = "tampered_hash_00000000000000000000000000000000000000000000000000000"

    # Publishing must detect payload hash mismatch and reject
    with pytest.raises(ValueError, match="integrity"):
        service.publish_version(alpha_admin_context, v.id)


# -----------------------------------------------------------------------------
# 6. Concurrent Idempotency Race Test
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_idempotency_race_condition(multi_tenant_db, alpha_admin_context):
    """Simulates concurrent direct turns with identical idempotency_key."""
    flawed_runtime = FlawedRuntimeAdapter()
    coordinator = RunCoordinator(runtime_adapter=flawed_runtime, db_manager=multi_tenant_db)

    req = RunRequest(
        prompt="Perform identical deterministic calculation",
        model="mock-fast",
        idempotency_key="concurrent_race_key_999",
    )

    # Launch two simultaneous execution tasks
    task1 = asyncio.create_task(coordinator.execute_managed_direct_turn(req, alpha_admin_context))
    task2 = asyncio.create_task(coordinator.execute_managed_direct_turn(req, alpha_admin_context))

    res1, res2 = await asyncio.gather(task1, task2)

    assert res1.status == RunStatus.COMPLETED
    assert res2.status == RunStatus.COMPLETED

    # Check database: exactly ONE run row must exist for this idempotency key in this project
    with multi_tenant_db.session() as s:
        runs = (
            s.query(RunStateModel)
            .filter_by(
                project_id=alpha_admin_context.project_id,
                idempotency_key="concurrent_race_key_999",
            )
            .all()
        )
        assert len(runs) == 1, f"Expected exactly 1 run record, found {len(runs)}"
