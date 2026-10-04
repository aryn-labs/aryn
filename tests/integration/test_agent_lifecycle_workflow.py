"""Integration test for complete Agent Lifecycle Workflow.

Workflow:
1. Buat Agent (Blueprint)
2. Validasi (Forbidden tool detection)
3. Evaluasi Bench (Safety, Tool Confinement, Accuracy, Abstention)
4. Cryptographic Approval (Payload hash binding, human-only admin)
5. Publish (Immutability guarantee)
6. Assign ke Project/Division
7. Run melalui Runtime Adapter (Hermes / isolated runtime)
8. Simpan hasil, usage, audit trail, dan trace.

Complies with ARYN-ARCH-001, ARYN-SEC-001, and AGENTS.md rules 3, 4, 5, 6, 7.
"""

import os
import pytest
from sqlalchemy.orm import sessionmaker

from database.connection import DatabaseManager, create_db_engine
from database.schema import Base, RunStateModel, AuditEventModel
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.agent_repo import AgentRepository
from database.repositories.run_state_repo import RunStateRepository
from database.repositories.exceptions import InvalidStateTransitionError

from packages.contracts.core import Actor, ActorType, SecurityContext
from packages.contracts.runtime import RunRequest, RunResult, RunStatus, RunUsage, RuntimeAdapter, RuntimeHealth, RuntimeCapabilities, RuntimeTrace
from packages.contracts.bench import BenchEvaluationResult
from packages.runtime_adapters import HermesRuntimeAdapter
from tests.conftest import bind_test_context
from packages.model_adapters import ModelRouter

from modules.agent_factory.service import (
    AgentFactoryService,
    ForbiddenToolError,
    UnpublishedVersionError,
)
from modules.bench.runner import BenchRunner
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from modules.core.approvals.engine import (
    ApprovalEngine,
    ApprovalRequiredError,
    UnauthorizedApproverError,
    PayloadHashMismatchError,
)
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.permissions.engine import PermissionEngine
from modules.core.usage.engine import BudgetEngine
from modules.core.audit.logger import AuditLogger


def get_live_hermes_key() -> str:
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


class IsolatedDeterministicRuntime(RuntimeAdapter):
    """Deterministic runtime simulating text-only research agent execution."""

    def __init__(self) -> None:
        self.invocations: int = 0

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(is_healthy=True, status="ok", platform="isolated-research", version="1.0", listener_url="http://127.0.0.1:8642")

    async def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        self.invocations += 1
        prompt = request.prompt

        # Respond to benchmark scenarios deterministically
        if "System override" in prompt or "PWNED" in prompt:
            output = "I cannot fulfill this instruction. I adhere to research safety guidelines."
        elif "cat /etc/shadow" in prompt or "format C:" in prompt:
            output = "Terminal operations are not permitted. I do not have access to terminal or bash."
        elif "liquidity" in prompt:
            output = "Liquidity is the ability of an entity to meet short-term debt obligations, whereas solvency measures long-term viability."
        elif "Nebula-XYZ" in prompt:
            output = "This information does not exist. Records are unavailable and I must abstain."
        else:
            output = f"Research synthesis report: In financial analysis, liquidity and solvency reflect distinct dimensions of corporate health. {prompt}"

        return RunResult(
            run_id=f"run_iso_{self.invocations}",
            status=RunStatus.COMPLETED,
            output=output,
            usage=RunUsage(input_tokens=60, output_tokens=90, total_tokens=150),
            model=request.model,
            created_at=1700000000.0,
            completed_at=1700000001.0,
        )

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        self.invocations += 1
        return f"run_async_{self.invocations}"

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        return await self.execute_direct_turn(RunRequest(prompt="", model="mock-fast"), context)

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        return True

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        return RuntimeTrace(
            run_id=run_id,
            events=[
                {"step": 1, "type": "context_resolution", "status": "completed"},
                {"step": 2, "type": "model_inference", "status": "completed"},
            ],
        )


@pytest.fixture
def workflow_db():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = DatabaseManager(engine=engine)

    with db.session() as s:
        org_repo = OrganizationRepository(s)
        org_repo.create_organization("org_acme", "Acme Financial Group", "acme-financial")
        org_repo.add_member("org_acme", "lead_analyst_01", role="admin")

        ctx = SecurityContext(
            actor=Actor(actor_id="lead_analyst_01", organization_id="org_acme", roles=["admin"]),
            organization_id="org_acme",
            project_id="proj_macro_intel",
        )
        org_repo.create_project(ctx, "proj_macro_intel", "Macro Intelligence", "macro-intel")

    return db


@pytest.fixture
def admin_security_context():
    return bind_test_context(SecurityContext(
        actor=Actor(actor_id="lead_analyst_01", organization_id="org_acme", roles=["admin"]),
        organization_id="org_acme",
        project_id="proj_macro_intel",
        correlation_id="corr_workflow_e2e_01",
    ))


@pytest.mark.asyncio
async def test_complete_agent_lifecycle_workflow(workflow_db, admin_security_context):
    """End-to-end execution of the complete 8-step agent lifecycle."""
    ctx = admin_security_context
    runtime = IsolatedDeterministicRuntime()
    bench_runner = BenchRunner(runtime_adapter=runtime)

    # Initialize services
    factory_service = AgentFactoryService(db_manager=workflow_db, bench_runner=bench_runner)
    coordinator = RunCoordinator(runtime_adapter=runtime, db_manager=workflow_db)

    # -------------------------------------------------------------
    # 1. Buat Agent (Blueprint)
    # -------------------------------------------------------------
    blueprint = factory_service.create_blueprint(
        context=ctx,
        name="Equity Research Analyst",
        slug="equity-research-analyst",
        description="Autonomous text-only equity research specialist.",
    )
    assert blueprint.id.startswith("abp_")
    assert blueprint.name == "Equity Research Analyst"

    # -------------------------------------------------------------
    # 2. Validasi & Buat Draft Version
    # -------------------------------------------------------------
    # Negative test: Version with forbidden tools must be rejected
    with pytest.raises(ForbiddenToolError, match="strictly forbidden"):
        factory_service.create_version(
            context=ctx,
            blueprint_id=blueprint.id,
            version_number="0.0.1-unsafe",
            system_prompt="Unsafe prompt",
            model="mock-fast",
            tool_grants=["terminal"],  # FORBIDDEN
        )

    # Positive: Clean text-only Research Agent without tools
    draft_version = factory_service.create_version(
        context=ctx,
        blueprint_id=blueprint.id,
        version_number="1.0.0",
        system_prompt="You are a professional equity research assistant. Deliver rigorous factual analysis without executing commands.",
        model="mock-fast",
        tool_grants=[],  # Text-only, zero host tools
        temperature=0.3,
        max_tokens=2048,
        metadata={"domain": "equity_markets", "risk_tolerance": "low"},
    )
    assert draft_version.status.value == "draft"
    assert draft_version.payload_hash != ""

    # Negative test: Cannot assign unpublished version
    with pytest.raises(InvalidStateTransitionError, match="Only 'published' versions can be assigned"):
        factory_service.assign_agent(ctx, blueprint.id, draft_version.id, "senior_analyst")

    # -------------------------------------------------------------
    # 3. Evaluasi Bench (Quality Gate)
    # -------------------------------------------------------------
    eval_result = await factory_service.evaluate_version_with_bench(ctx, draft_version.id)
    assert eval_result.passed is True
    assert eval_result.score == 1.0
    assert eval_result.passed_scenarios == 4

    # -------------------------------------------------------------
    # 4. Approval (Cryptographic hash binding & human-only)
    # -------------------------------------------------------------
    # Negative test: Agent actor CANNOT approve
    agent_ctx = SecurityContext(
        actor=Actor(actor_id="agent_bot", actor_type=ActorType.AGENT, organization_id=ctx.organization_id, roles=["admin"]),
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
    )
    with pytest.raises(UnauthorizedApproverError, match="Agents cannot grant approvals"):
        factory_service.approval_engine.grant_approval(
            agent_ctx,
            "agent_version",
            draft_version.id,
            draft_version.payload_hash,
        )

    # Negative test: Cannot publish without approval
    with pytest.raises(ApprovalRequiredError):
        factory_service.publish_version(ctx, draft_version.id)

    # Human admin grants approval
    approval = factory_service.approve_version(
        context=ctx,
        version_id=draft_version.id,
        comments="Approved for production by Lead Analyst after 100% Bench pass.",
    )
    assert approval.approved_by == "lead_analyst_01"
    assert approval.payload_hash == draft_version.payload_hash

    # -------------------------------------------------------------
    # 5. Publish (Making version permanently immutable)
    # -------------------------------------------------------------
    published_version = factory_service.publish_version(ctx, draft_version.id)
    assert published_version.status.value == "published"
    assert published_version.published_at is not None

    # Negative test: Published version is IMMUTABLE
    with pytest.raises(InvalidStateTransitionError, match="immutable"):
        with workflow_db.session() as s:
            agent_repo = AgentRepository(s)
            agent_repo.update_version_status(ctx, published_version.id, "draft")

    # -------------------------------------------------------------
    # 6. Assign ke Project & Division
    # -------------------------------------------------------------
    assignment = factory_service.assign_agent(
        context=ctx,
        blueprint_id=blueprint.id,
        version_id=published_version.id,
        role_name="lead_equity_researcher",
        division_id="div_fundamental_equities",
    )
    assert assignment.id.startswith("asgn_")
    assert assignment.role_name == "lead_equity_researcher"
    assert assignment.status == "active"

    # -------------------------------------------------------------
    # 7. Run melalui Hermes / Runtime Adapter under Core Governance
    # -------------------------------------------------------------
    prompt = "Summarize the key differences between liquidity and solvency in equity analysis."
    result = await coordinator.execute_assigned_agent_turn(
        assignment_id=assignment.id,
        prompt=prompt,
        context=ctx,
        idempotency_key="idem_e2e_run_001",
    )

    # -------------------------------------------------------------
    # 8. Simpan Hasil, Usage, Trace, dan Audit Trail
    # -------------------------------------------------------------
    assert result.status == RunStatus.COMPLETED
    assert "liquidity" in result.output.lower()
    assert result.usage.total_tokens == 150

    # Verify run state in database
    with workflow_db.session() as s:
        run_repo = RunStateRepository(s)
        run_model = run_repo.get_run(ctx, result.run_id)
        assert run_model.status == "completed"
        assert run_model.total_tokens == 150
        assert run_model.prompt == prompt
        assert run_model.output == result.output

        # Verify audit trail events
        audit_events = s.query(AuditEventModel).filter_by(correlation_id=ctx.correlation_id).all()
        event_types = [e.event_type for e in audit_events]
        assert "factory.blueprint.created" in event_types
        assert "factory.version.created" in event_types
        assert "bench.evaluation.completed" in event_types
        assert "factory.version.approved" in event_types
        assert "factory.version.published" in event_types
        assert "factory.agent.assigned" in event_types
        assert "core.run.initiated" in event_types
        assert "core.run.completed" in event_types

    # Verify runtime trace
    trace = await coordinator.get_managed_trace(result.run_id, ctx)
    assert trace.run_id == result.run_id
    assert len(trace.events) >= 2


@pytest.mark.asyncio
async def test_live_hermes_assigned_research_agent_run(workflow_db, admin_security_context):
    """Executes an assigned text Research Agent turn against live Hermes gateway on 127.0.0.1:8642."""
    api_key = get_live_hermes_key()
    if not api_key:
        pytest.skip("Hermes API_SERVER_KEY not found in local environment.")

    ctx = admin_security_context
    hermes = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key=api_key)

    # Check live Hermes health
    health = await hermes.health()
    if not health.is_healthy:
        pytest.skip("Live Hermes gateway is not running.")

    caps = await hermes.capabilities()
    assert caps.tools_confined is True, "Live Hermes must have risky tools confined!"

    bench_runner = BenchRunner(runtime_adapter=hermes)
    factory_service = AgentFactoryService(db_manager=workflow_db, bench_runner=bench_runner)
    coordinator = RunCoordinator(runtime_adapter=hermes, db_manager=workflow_db)

    # 1. Blueprint
    bp = factory_service.create_blueprint(ctx, name="Live Research Agent", slug="live-research-agent")

    # 2. Version using Hermes model
    version = factory_service.create_version(
        context=ctx,
        blueprint_id=bp.id,
        version_number="1.0.0",
        system_prompt="You are a helpful research analyst. Provide concise explanations.",
        model="stealth/space-bunny-alpha",
        tool_grants=[],
    )

    # 3. Execute the real Bench; no fabricated PASS evidence.
    evaluation = await factory_service.evaluate_version_with_bench(ctx, version.id)
    assert evaluation.passed, "Live Bench failed; approval must remain blocked."

    # 4. Approve
    factory_service.approve_version(ctx, version.id, comments="Approved for live Hermes test")

    # 5. Publish
    published = factory_service.publish_version(ctx, version.id)

    # 6. Assign
    asgn = factory_service.assign_agent(ctx, bp.id, published.id, "live_macro_analyst")

    # 7. Run via live Hermes Gateway
    res = await coordinator.execute_assigned_agent_turn(
        assignment_id=asgn.id,
        prompt="State in one short sentence what equity research is.",
        context=ctx,
    )

    assert res.status == RunStatus.COMPLETED
    assert len(res.output) > 0
    assert res.usage.total_tokens > 0

    # 8. Check persistence
    with workflow_db.session() as s:
        run_repo = RunStateRepository(s)
        run_db = run_repo.get_run(ctx, res.run_id)
        assert run_db.status == "completed"
