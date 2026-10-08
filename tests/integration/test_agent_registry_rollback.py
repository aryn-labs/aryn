"""AF-07: exact immutable publication activation, rollback and durable run identity."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.bench_regression_repo import BenchRegressionRepository
from database.repositories.run_state_repo import RunStateRepository
from database.schema import (AgentAssignmentModel, AssignmentTransitionModel,
    RunStateModel, AuditEventModel)
from modules.core.workflows.coordinator import RunCoordinator
from database.repositories.exceptions import InvalidStateTransitionError
from packages.contracts.agent import RollbackIntent
from modules.core.history import HistoryUnverifiedError
from tests.storage_attacks import corrupt_storage


async def publications(lifecycle):
    db, ctx, runtime, factory, bp, first = lifecycle
    await factory.evaluate_version_with_bench(ctx, first.id)
    factory.approve_version(ctx, first.id)
    first = factory.publish_version(ctx, first.id)
    second = factory.create_version(ctx, bp.id, "2.0.0", "Second publication: follow research safety guidelines.", "mock-fast",
        temperature=0.2, max_tokens=512)
    await factory.evaluate_version_with_bench(ctx, second.id)
    factory.approve_version(ctx, second.id)
    second = factory.publish_version(ctx, second.id)
    assignment = factory.assign_agent(ctx, bp.id, second.id, "Research A")
    intent = RollbackIntent(target_version_id=first.id, expected_current_version_id=second.id,
        expected_transition_id=assignment.current_transition_id, reason="Restore reviewed previous publication.",
        idempotency_key="rollback-request-001")
    return db, ctx, runtime, factory, bp, first, second, assignment, intent


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
async def test_registry_rollback_preserves_artifacts_baseline_and_run_provenance(lifecycle):
    db, ctx, runtime, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    older = factory.assign_agent(ctx, bp.id, first.id, "Original publication")
    other = factory.assign_agent(ctx, bp.id, second.id, "Research B")
    core = RunCoordinator(runtime, db_manager=db)
    original = await core.execute_assigned_agent_turn(older.id, "Original run", ctx, "original-run-request")
    assert original.agent_version_id == first.id
    before = await core.execute_assigned_agent_turn(assignment.id, "Before rollback", ctx, "before-run-request")
    assert before.agent_version_id == second.id
    with db.session() as session:
        baseline = BenchRegressionRepository(session, db.evidence_signer).current(ctx, bp.id)
        versions_before = [tuple(session.execute(text("SELECT * FROM agent_versions WHERE id=:id"), {"id": v.id}).one()) for v in (first, second)]
        baseline_history = session.execute(text("SELECT * FROM bench_baselines ORDER BY generation")).all()
    transition = factory.rollback_assignment(ctx, assignment.id, intent)
    assert transition.from_version_id == second.id and transition.to_version_id == first.id
    repeated = factory.rollback_assignment(ctx, assignment.id, intent)
    assert repeated == transition
    after = await core.execute_assigned_agent_turn(assignment.id, "After rollback", ctx, "after-run-request")
    assert after.agent_version_id == first.id and after.agent_payload_hash == first.payload_hash
    request = runtime.requests[-1]
    assert (request.system_instructions, request.model, request.temperature, request.max_tokens) == (
        first.system_prompt, first.model, first.temperature, first.max_tokens)
    registry = {r.version_id: r for r in factory.version_registry(ctx, bp.id)}
    assert registry[first.id].rollback_eligible and registry[second.id].rollback_eligible
    assert registry[first.id].active_assignment_count == 2 and registry[second.id].active_assignment_count == 1
    assert registry[second.id].current_baseline and not registry[first.id].current_baseline
    with db.session() as session:
        repo = AgentActivationRepository(session, db.evidence_signer)
        assignment_row = session.get(AgentAssignmentModel, assignment.id)
        history = repo.history(ctx, assignment_row)
        assert [h.transition_type for h in history] == ["initial", "rollback"]
        assert session.get(AgentAssignmentModel, other.id).version_id == second.id
        assert BenchRegressionRepository(session, db.evidence_signer).current(ctx, bp.id) == baseline
        assert session.execute(text("SELECT * FROM bench_baselines ORDER BY generation")).all() == baseline_history
        assert [tuple(session.execute(text("SELECT * FROM agent_versions WHERE id=:id"), {"id": v.id}).one()) for v in (first, second)] == versions_before
        run_repo = RunStateRepository(session)
        assert run_repo.get_run(ctx, before.run_id).agent_version_id == second.id
        assert run_repo.get_run(ctx, after.run_id).agent_version_id == first.id
        assert run_repo.verify_assignment_provenance(session.get(RunStateModel, after.run_id))
        assert session.query(AuditEventModel).filter_by(event_type="factory.assignment.rollback_committed").count() == 1
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
async def test_generic_suite_publication_remains_known_good(lifecycle, monkeypatch):
    from tests.bench_fixtures import create_generic_version
    db, ctx, runtime, factory, bp, version = create_generic_version(lifecycle, monkeypatch)
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    factory.publish_version(ctx, version.id)
    registry = factory.version_registry(ctx, bp.id)
    assert registry[0].rollback_eligible and registry[0].evaluation_id == evaluation.evaluation_id
    assignment = factory.assign_agent(ctx, bp.id, version.id, "Generic analysis")
    assert factory.get_assignment(ctx, assignment.id).version_id == version.id


@pytest.mark.asyncio
async def test_in_flight_run_keeps_claimed_version_across_rollback(lifecycle):
    db, ctx, runtime, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    started, release = asyncio.Event(), asyncio.Event()
    actual_execute = runtime.execute_direct_turn
    async def waiting(request, context):
        started.set()
        await release.wait()
        return await actual_execute(request, context)
    runtime.execute_direct_turn = waiting
    core = RunCoordinator(runtime, db_manager=db)
    task = asyncio.create_task(core.execute_assigned_agent_turn(assignment.id, "In-flight request", ctx, "in-flight-request"))
    await started.wait()
    with db.session() as session:
        row = session.query(RunStateModel).filter_by(idempotency_key="in-flight-request").one()
        assert row.agent_version_id == second.id and row.status == "started"
    factory.rollback_assignment(ctx, assignment.id, intent)
    release.set()
    result = await task
    assert result.agent_version_id == second.id and runtime.requests[-1].system_instructions == second.system_prompt
    result = await core.execute_assigned_agent_turn(assignment.id, "New request", ctx, "new-run-request-key")
    assert result.agent_version_id == first.id


@pytest.mark.asyncio
async def test_concurrent_identical_rollback_has_one_transition(lifecycle):
    db, ctx, _, factory, _, first, _, assignment, intent = await publications(lifecycle)
    def commit():
        return factory.rollback_assignment(ctx, assignment.id, intent).transition_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(lambda _: commit(), range(2)))
    assert identities[0] == identities[1]
    with db.session() as session:
        assert session.query(AssignmentTransitionModel).filter_by(assignment_id=assignment.id).count() == 2
        assert session.get(AgentAssignmentModel, assignment.id).version_id == first.id


@pytest.mark.asyncio
async def test_concurrent_different_rollback_intents_use_current_authoritative_activation(lifecycle):
    db, ctx, _, factory, _, _, _, assignment, intent = await publications(lifecycle)
    def commit(index):
        try:
            return factory.rollback_assignment(ctx, assignment.id,
                intent.model_copy(update={"idempotency_key": f"separate-intent-{index}"})).transition_id
        except InvalidStateTransitionError:
            return "stale"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, range(2)))
    assert outcomes.count("stale") == 1
    with db.session() as session:
        assert session.query(AssignmentTransitionModel).filter_by(assignment_id=assignment.id).count() == 2


@pytest.mark.asyncio
async def test_atomic_rollback_failure_does_not_leave_pointer_or_partial_audit(lifecycle, monkeypatch):
    db, ctx, _, factory, _, _, second, assignment, intent = await publications(lifecycle)
    from modules.core.audit.logger import AuditLogger
    original = AuditLogger.record
    def fail(self, event_type, *args, **kwargs):
        if event_type == "factory.assignment.rollback_committed":
            raise RuntimeError("Audit storage unavailable")
        return original(self, event_type, *args, **kwargs)
    monkeypatch.setattr(AuditLogger, "record", fail)
    with pytest.raises(RuntimeError, match="Audit storage"):
        factory.rollback_assignment(ctx, assignment.id, intent)
    with db.session() as session:
        assert session.get(AgentAssignmentModel, assignment.id).version_id == second.id
        assert session.query(AssignmentTransitionModel).filter_by(assignment_id=assignment.id).count() == 1
        assert session.query(AuditEventModel).filter_by(event_type="factory.assignment.rollback_requested").count() == 0
        assert session.query(AuditEventModel).filter_by(event_type="factory.assignment.rollback_denied").count() == 1


@pytest.mark.asyncio
async def test_deleted_history_cannot_be_adopted_as_pre_existing_assignment(lifecycle):
    db, ctx, _, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    with corrupt_storage(db.engine) as connection:
        connection.execute(text("DELETE FROM assignment_transitions WHERE assignment_id=:id"), {"id": assignment.id})
        connection.execute(text("UPDATE agent_assignments SET current_transition_id=NULL,activation_origin='legacy' WHERE id=:id"), {"id": assignment.id})
    intent = intent.model_copy(update={"expected_transition_id": None})
    with pytest.raises(HistoryUnverifiedError):
        factory.rollback_assignment(ctx, assignment.id, intent)
    with db.session() as session:
        assert session.query(AssignmentTransitionModel).filter_by(assignment_id=assignment.id).count() == 0
    assert factory.get_assignment(ctx, assignment.id).version_id == second.id


@pytest.mark.asyncio
async def test_new_publication_without_receipt_cannot_use_historical_fallback(lifecycle):
    db, ctx, _, factory, bp, first, _, _, _ = await publications(lifecycle)
    with corrupt_storage(db.engine) as connection:
        connection.execute(text("DELETE FROM agent_publications WHERE version_id=:id"), {"id": first.id})
    registry = {entry.version_id: entry for entry in factory.version_registry(ctx, bp.id)}
    assert not registry[first.id].rollback_eligible
    assert "historical_access_read_only" in registry[first.id].limitations


@pytest.mark.asyncio
async def test_explicit_baseline_before_publication_is_not_known_good_until_published(lifecycle):
    db, ctx, _, factory, bp, first = lifecycle
    result = await factory.evaluate_version_with_bench(ctx, first.id)
    with db.session(write=True) as session:
        BenchRegressionRepository(session, db.evidence_signer).accept(ctx, result.evaluation_id, reason="Reviewed evaluation baseline.")
    assert not factory.version_registry(ctx, bp.id)[0].rollback_eligible
    factory.approve_version(ctx, first.id)
    factory.publish_version(ctx, first.id)
    assert factory.version_registry(ctx, bp.id)[0].rollback_eligible
