"""Run ownership must be checked before any runtime access or cancellation."""

import pytest
from sqlalchemy import text

from database.repositories.exceptions import EntityNotFoundError, TenantIsolationError
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.run_state_repo import RunStateRepository
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.workflows.coordinator import RunCoordinator
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RuntimeTrace,
    RunUsage,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get_managed_result", "cancel_managed_run", "get_managed_trace"])
async def test_other_project_is_denied_before_runtime_access(lifecycle, operation):
    db, ctx, runtime, factory, bp, version = lifecycle
    with db.session() as s:
        OrganizationRepository(s).create_project(ctx, "other", "Other", "other")
    from tests.conftest import bind_test_context
    foreign = bind_test_context(ctx.model_copy(update={"project_id": "other"}, deep=True))
    calls = []
    async def result(run_id, context):
        calls.append(run_id)
        return RunResult(run_id=run_id, status=RunStatus.COMPLETED, output="private", model="mock-fast", created_at=1)
    async def cancel(run_id, context):
        calls.append(run_id)
        return True
    async def trace(run_id, context):
        calls.append(run_id)
        return RuntimeTrace(run_id=run_id)
    runtime.get_result, runtime.cancel_run, runtime.get_trace = result, cancel, trace
    coordinator = RunCoordinator(runtime, db_manager=db)
    run_id = await coordinator.start_managed_run(RunRequest(prompt="Research", model="mock-fast"), ctx)
    with pytest.raises(TenantIsolationError):
        await getattr(coordinator, operation)(run_id, foreign)
    assert calls == []


@pytest.mark.asyncio
async def test_rejected_cancellation_does_not_claim_cancelled_state(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    coordinator = RunCoordinator(runtime, db_manager=db)
    run_id = await coordinator.start_managed_run(RunRequest(prompt="Research", model="mock-fast"), ctx)
    assert not await coordinator.cancel_managed_run(run_id, ctx)
    with db.session() as s:
        assert RunStateRepository(s).get_run(ctx, run_id).status != "cancelled"


@pytest.mark.asyncio
async def test_corrupted_assignment_blueprint_cannot_execute(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    factory.publish_version(ctx, version.id)
    assignment = factory.assign_agent(ctx, bp.id, version.id, "researcher")
    other = factory.create_blueprint(ctx, "Other", "other")
    with db.session() as s:
        s.execute(text("UPDATE agent_assignments SET blueprint_id=:bp WHERE id=:id"), {"bp": other.id, "id": assignment.id})
    before = len(runtime.requests)
    with pytest.raises(PermissionDeniedError, match="blueprint|Blueprint"):
        await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Research", ctx)
    assert len(runtime.requests) == before


@pytest.mark.asyncio
async def test_result_mapping_and_terminal_cache_account_usage_once(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    calls = []
    async def result(runtime_id, context):
        calls.append(runtime_id)
        return RunResult(run_id=runtime_id, status=RunStatus.COMPLETED, output="Actual result",
                         model="mock-fast", created_at=1, usage=RunUsage(input_tokens=2, output_tokens=3, total_tokens=5))
    runtime.get_result = result
    coordinator = RunCoordinator(runtime, db_manager=db)
    core_id = await coordinator.start_managed_run(RunRequest(prompt="Research", model="mock-fast"), ctx)
    result = await coordinator.get_managed_result(core_id, ctx)
    assert result.run_id == core_id
    assert calls == ["test_only"]
    cached = await RunCoordinator(runtime, db_manager=db).get_managed_result(core_id, ctx)
    assert cached.output == result.output
    assert calls == ["test_only"]
    with db.session() as s:
        assert s.execute(text("SELECT cumulative_tokens FROM usage_budgets")).scalar() == 5
        assert s.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
async def test_stop_acknowledgment_is_not_cancellation_proof(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    ids = []
    status = RunStatus.STOPPING
    async def cancel(runtime_id, context):
        ids.append(runtime_id)
        return True
    async def result(runtime_id, context):
        return RunResult(run_id=runtime_id, status=status, output="", model="mock-fast", created_at=1)
    runtime.cancel_run, runtime.get_result = cancel, result
    coordinator = RunCoordinator(runtime, db_manager=db)
    core_id = await coordinator.start_managed_run(RunRequest(prompt="Research", model="mock-fast"), ctx)
    assert not await coordinator.cancel_managed_run(core_id, ctx)
    with db.session() as s:
        assert RunStateRepository(s).get_run(ctx, core_id).status == "stopping"
        assert s.execute(text("SELECT COUNT(*) FROM audit_events WHERE status='cancelled'")).scalar() == 0
    status = RunStatus.CANCELLED
    assert await coordinator.cancel_managed_run(core_id, ctx)
    assert ids == ["test_only", "test_only"]
    with db.session() as s:
        assert RunStateRepository(s).get_run(ctx, core_id).status == "cancelled"


@pytest.mark.asyncio
async def test_direct_trace_and_cancellation_are_explicitly_unavailable(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    coordinator = RunCoordinator(runtime, db_manager=db)
    result = await coordinator.execute_managed_direct_turn(RunRequest(prompt="Research", model="mock-fast"), ctx)
    trace = await coordinator.get_managed_trace(result.run_id, ctx)
    assert not trace.available and trace.events == [] and trace.unavailability_reason
    assert not await coordinator.cancel_managed_run(result.run_id, ctx)
    with pytest.raises(EntityNotFoundError):
        await coordinator.get_managed_result("missing", ctx)


@pytest.mark.asyncio
async def test_assignment_requires_real_published_governance_evidence(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    # Out-of-band forged lifecycle state must still fail execution governance.
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET status='published' WHERE id=:id"), {"id": version.id})
    with pytest.raises(QualityGateFailedError):
        factory.assign_agent(ctx, bp.id, version.id, "researcher")
    assert runtime.requests == []


@pytest.mark.asyncio
async def test_recovery_is_project_scoped_and_never_claims_runtime_cancellation(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    with db.session() as s:
        OrganizationRepository(s).create_project(ctx, "other", "Other", "other")
    from tests.conftest import bind_test_context
    other = bind_test_context(ctx.model_copy(update={"project_id": "other"}, deep=True))
    coordinator = RunCoordinator(runtime, db_manager=db)
    own_id = await coordinator.start_managed_run(RunRequest(prompt="Own", model="mock-fast", idempotency_key="own-key"), ctx)
    other_id = await coordinator.start_managed_run(RunRequest(prompt="Other", model="mock-fast"), other)
    assert coordinator.recover_in_flight_runs(ctx) == []  # Live owner is never abandoned.
    from database.connection import DatabaseManager, create_db_engine
    db.engine.dispose()
    db = DatabaseManager(create_db_engine(str(db.engine.url)))
    coordinator = RunCoordinator(runtime, db_manager=db)
    recovered = coordinator.recover_in_flight_runs(ctx)
    assert [x["run_id"] for x in recovered] == [own_id]
    assert recovered[0]["runtime_outcome"] == "unknown"
    assert recovered[0]["cancellation_confirmed"] is False
    with db.session() as s:
        assert RunStateRepository(s).get_run(other, other_id).status == "started"
        assert RunStateRepository(s).get_run(ctx, own_id).status == "outcome_unknown"
    before = len(runtime.requests)
    result = await coordinator.start_managed_run(RunRequest(prompt="Own", model="mock-fast", idempotency_key="own-key"), ctx)
    assert result == own_id and len(runtime.requests) == before
    db.engine.dispose()
