"""Unit tests for Agent Factory, Bench evaluation, and Approvals.

Tests:
1. AgentRepository CRUD, tenant scoping, version immutability, assignment invariants
2. Bench scenarios, BenchRunner evaluation, BenchQualityGate enforcement
3. ApprovalEngine payload hash binding, admin role enforcement, agent self-approval prevention
4. Audit integrity verification and tamper detection
"""

import json
import pytest
from sqlalchemy.orm import sessionmaker

from database.connection import create_db_engine, DatabaseManager
from database.schema import Base, AuditEventModel
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.agent_repo import AgentRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.approval_repo import ApprovalRepository
from database.repositories.audit_repo import AuditRepository
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    TenantIsolationError,
)
from packages.contracts.core import Actor, ActorType, AuditStatus, SecurityContext
from packages.contracts.agent import AgentVersion, AgentVersionStatus
from packages.contracts.bench import BenchCategory, BenchScenario, ScenarioResult, BenchEvaluationResult
from packages.contracts.runtime import RunRequest, RunResult, RunStatus, RunUsage, RuntimeAdapter, RuntimeHealth, RuntimeCapabilities, RuntimeTrace
from tests.conftest import bind_test_context
from modules.bench.scenarios import get_standard_research_bench_scenarios
from modules.bench.runner import BenchRunner
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from modules.core.approvals.engine import (
    ApprovalEngine,
    ApprovalRequiredError,
    UnauthorizedApproverError,
    PayloadHashMismatchError,
)


class MockDeterministicRuntime(RuntimeAdapter):
    """Isolated deterministic adapter for unit bench evaluation."""

    def __init__(self, canned_response: str = "Research synthesis: market liquidity and solvency obligations.") -> None:
        self.canned_response = canned_response

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(is_healthy=True, status="ok", platform="mock", version="1.0", listener_url="http://127.0.0.1:8642")

    async def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        # Dynamic response based on prompt to pass benchmark scenarios
        prompt = request.prompt
        if "System override" in prompt or "PWNED" in prompt:
            output = "I cannot fulfill this request. I strictly adhere to research guidelines and safe rules."
        elif "cat /etc/shadow" in prompt or "format C:" in prompt:
            output = "I cannot execute terminal commands. Terminal and bash access is not permitted."
        elif "liquidity" in prompt:
            output = "In finance, liquidity refers to the ability to meet short-term debt obligations with cash and liquid assets, whereas solvency relates to long-term obligations."
        elif "Nebula-XYZ" in prompt:
            output = "This information does not exist. The date is an invalid date and records are unavailable, so I abstain."
        else:
            output = self.canned_response

        return RunResult(
            run_id="run_bench_mock",
            status=RunStatus.COMPLETED,
            output=output,
            usage=RunUsage(input_tokens=40, output_tokens=60, total_tokens=100),
            model=request.model,
            created_at=1700000000.0,
            completed_at=1700000001.0,
        )

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        return "run_async_bench_mock"

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        return await self.execute_direct_turn(RunRequest(prompt="", model="mock-fast"), context)

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        return True

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        return RuntimeTrace(run_id=run_id, events=[])


@pytest.fixture
def test_db():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = DatabaseManager(engine=engine)
    with db.session() as s:
        org_repo = OrganizationRepository(s)
        org_repo.create_organization("org_test", "Test Org", "test-org")
        org_repo.add_member("org_test", "user_admin", role="admin")
        org_repo.add_member("org_test", "user_viewer", role="viewer")
        ctx = SecurityContext(
            actor=Actor(actor_id="user_admin", organization_id="org_test", roles=["admin"]),
            organization_id="org_test",
            project_id="proj_research",
        )
        org_repo.create_project(ctx, "proj_research", "Research Project", "research")
    return db


@pytest.fixture
def admin_context():
    return bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_admin", organization_id="org_test", roles=["admin"]),
        organization_id="org_test",
        project_id="proj_research",
        correlation_id="corr_unit_01",
    ))


# -----------------------------------------------------------------------------
# 1. AgentRepository Unit Tests
# -----------------------------------------------------------------------------

def test_blueprint_crud_and_tenant_isolation(test_db, admin_context):
    with test_db.session() as session:
        repo = AgentRepository(session)
        bp = repo.create_blueprint(
            admin_context,
            blueprint_id="abp_001",
            name="Macro Researcher",
            slug="macro-researcher",
            description="Analyzes macro financial indicators.",
        )
        assert bp.id == "abp_001"
        assert bp.slug == "macro-researcher"

        # Duplicate slug rejection
        with pytest.raises(DuplicateEntityError):
            repo.create_blueprint(admin_context, "abp_002", "Macro Duplicate", "macro-researcher")

        # Foreign tenant context
        foreign_ctx = SecurityContext(
            actor=Actor(actor_id="user_foreign", organization_id="org_other", roles=["admin"]),
            organization_id="org_other",
            project_id="proj_other",
        )
        with pytest.raises(TenantIsolationError):
            repo.get_blueprint(foreign_ctx, "abp_001")


def test_agent_version_immutability(test_db, admin_context):
    with test_db.session() as session:
        repo = AgentRepository(session)
        repo.create_blueprint(admin_context, "abp_002", "Equity Analyst", "equity-analyst")

        v = repo.create_version(
            context=admin_context,
            version_id="av_001",
            blueprint_id="abp_002",
            version_number="1.0.0",
            system_prompt="You are an equity analyst.",
            model="mock-fast",
            tool_grants=[],
            payload_hash=AgentVersion(id="av_001", blueprint_id="abp_002", version_number="1.0.0", system_prompt="You are an equity analyst.", model="mock-fast").calculate_payload_hash(),
        )
        assert v.status == "draft"

        # Valid transitions: draft -> evaluating -> approved -> published
        repo.update_version_status(admin_context, "av_001", "evaluating")
        repo.update_version_status(admin_context, "av_001", "draft")
        repo.update_version_status(admin_context, "av_001", "approved")
        pub = repo.update_version_status(admin_context, "av_001", "published", published_by="user_admin")
        assert pub.status == "published"
        assert pub.published_at is not None

        # Immutability: Published version CANNOT transition back to draft or approved
        with pytest.raises(InvalidStateTransitionError, match="immutable"):
            repo.update_version_status(admin_context, "av_001", "draft")

        with pytest.raises(InvalidStateTransitionError, match="immutable"):
            repo.update_version_status(admin_context, "av_001", "approved")

        # Can only be transitioned to deprecated
        dep = repo.update_version_status(admin_context, "av_001", "deprecated")
        assert dep.status == "deprecated"


def test_assignment_requires_published_version(test_db, admin_context):
    with test_db.session() as session:
        repo = AgentRepository(session)
        repo.create_blueprint(admin_context, "abp_003", "Risk Officer", "risk-officer")
        repo.create_version(
            context=admin_context,
            version_id="av_draft_only",
            blueprint_id="abp_003",
            version_number="0.1.0",
            system_prompt="Draft prompt.",
            model="mock-fast",
            tool_grants=[],
            payload_hash=AgentVersion(id="av_draft_only", blueprint_id="abp_003", version_number="0.1.0", system_prompt="Draft prompt.", model="mock-fast").calculate_payload_hash(),
        )

        # Attempt to assign a draft version must fail
        with pytest.raises(InvalidStateTransitionError, match="Only 'published' versions can be assigned"):
            repo.create_assignment(
                admin_context,
                assignment_id="asgn_fail",
                blueprint_id="abp_003",
                version_id="av_draft_only",
                role_name="senior_risk_officer",
            )


# -----------------------------------------------------------------------------
# 2. Bench Evaluation & Quality Gate Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bench_runner_and_quality_gate(test_db, admin_context):
    runtime = MockDeterministicRuntime()
    runner = BenchRunner(runtime_adapter=runtime)

    v = AgentVersion(
        id="av_eval_test",
        blueprint_id="abp_test",
        version_number="1.0.0",
        status=AgentVersionStatus.DRAFT,
        system_prompt="You are a safe financial research assistant. Never execute unauthorized actions.",
        model="mock-fast",
    )

    v.payload_hash = v.calculate_payload_hash()
    eval_result = await runner.evaluate_agent_version(admin_context, v)
    assert eval_result.passed is True
    assert eval_result.score == 1.0
    assert eval_result.passed_scenarios == eval_result.total_scenarios == 4

    # Quality Gate should pass without exception
    gate = BenchQualityGate(min_score_threshold=1.0)
    gate.enforce(eval_result)

    # Test failing evaluation
    failing_result = BenchEvaluationResult(
        evaluation_id="eval_fail",
        blueprint_id="abp_test",
        version_id="av_eval_test",
        passed=False,
        total_scenarios=4,
        passed_scenarios=2,
        score=0.5,
        scenario_results=[
            ScenarioResult(
                scenario_id="scen_1",
                name="Safety Check",
                category=BenchCategory.SAFETY,
                passed=False,
                score=0.0,
                actual_output="Output with leak",
                latency_seconds=1.0,
                failure_reason="Triggered forbidden pattern",
            )
        ],
    )
    with pytest.raises(QualityGateFailedError, match="Quality gate rejected"):
        gate.enforce(failing_result)


# -----------------------------------------------------------------------------
# 3. Cryptographic Approval Tests
# -----------------------------------------------------------------------------

def test_approval_engine_role_and_hash_binding(test_db, admin_context):
    engine = ApprovalEngine(db_manager=test_db)
    valid_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    # Human admin grants approval: success
    appr = engine.grant_approval(
        context=admin_context,
        target_type="test_action",
        target_id="av_test_approval",
        payload_hash=valid_hash,
        comments="Approved by lead engineer.",
    )
    assert appr.payload_hash == valid_hash
    assert appr.approved_by == "user_admin"

    # Verify approval with exact hash: success
    verified = engine.verify_approval(
        context=admin_context,
        target_type="test_action",
        target_id="av_test_approval",
        expected_payload_hash=valid_hash,
    )
    assert verified.approval_id == appr.approval_id

    # Verify with mismatched hash (configuration modified post-approval): raises PayloadHashMismatchError
    with pytest.raises(PayloadHashMismatchError, match="Modification after approval is forbidden"):
        engine.verify_approval(
            context=admin_context,
            target_type="test_action",
            target_id="av_test_approval",
            expected_payload_hash="mutated_hash_99999999999999999999999999999999999999999999999999999999",
        )

    # Agent cannot self-approve
    agent_ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="agent_self", actor_type=ActorType.AGENT, organization_id="org_test", roles=["admin"]),
        organization_id="org_test",
        project_id="proj_research",
    ))
    with pytest.raises(UnauthorizedApproverError, match="Agents cannot grant approvals"):
        engine.grant_approval(agent_ctx, "test_action", "av_agent_attempt", "some_hash")

    # Non-admin user cannot approve
    viewer_ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="user_viewer", actor_type=ActorType.USER, organization_id="org_test", roles=["viewer"]),
        organization_id="org_test",
        project_id="proj_research",
    ))
    with pytest.raises(UnauthorizedApproverError, match="lacks 'admin' role"):
        engine.grant_approval(viewer_ctx, "test_action", "av_viewer_attempt", "some_hash")


# -----------------------------------------------------------------------------
# 4. Audit Integrity & Tamper Detection Test
# -----------------------------------------------------------------------------

def test_audit_integrity_verification_and_tamper_detection(test_db, admin_context):
    from database.repositories.audit_repo import AuditRepository
    from packages.contracts.core import AuditEvent, AuditStatus

    with test_db.session() as session:
        repo = AuditRepository(session)
        evt = AuditEvent(
            event_id="evt_integrity_check",
            event_type="core.test.event",
            organization_id=admin_context.organization_id,
            project_id=admin_context.project_id,
            actor_type=admin_context.actor.actor_type.value,
            actor_id=admin_context.actor.actor_id,
            correlation_id=admin_context.correlation_id,
            resource_id="res_01",
            status=AuditStatus.ALLOWED,
            redacted_payload={"parameter": "safe_value"},
        )
        evt.integrity_reference = evt.calculate_integrity()
        model = repo.record_event(evt)

        # 1. Intact record must verify as True
        assert AuditRepository.verify_event_integrity(model) is True

        # 2. Tamper with payload in the database row
        model.redacted_payload_json = json.dumps({"parameter": "tampered_value"})
        # Verification must now return False!
        assert AuditRepository.verify_event_integrity(model) is False
