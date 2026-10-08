"""AF-07: no unsafe activation through browser, repository or historical evidence."""
import pytest
from sqlalchemy import text

from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.agent_repo import AgentRepository
from database.repositories.exceptions import InvalidStateTransitionError, TenantIsolationError
from database.schema import (AgentAssignmentModel, AgentVersionModel, AgentPublicationModel,
    AssignmentTransitionModel)
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.approvals.engine import ApprovalRequiredError, PayloadHashMismatchError
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.workflows.coordinator import IdempotencyConflictError
from packages.contracts.agent import VersionIntegrityError
from packages.contracts.core import ActorType
from tests.conftest import bind_test_context
from tests.integration.test_agent_registry_rollback import publications
from tests.storage_attacks import corrupt_storage

DENIED = (ValueError, InvalidStateTransitionError, TenantIsolationError, QualityGateFailedError,
    ApprovalRequiredError, PayloadHashMismatchError, PermissionDeniedError)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "evaluating", "approved", "rejected", "deprecated"])
async def test_non_published_target_rejected(lifecycle, status):
    db, ctx, _, factory, _, first, second, assignment, intent = await publications(lifecycle)
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE agent_versions SET status=:status WHERE id=:id"), {"status": status, "id": first.id})
    with pytest.raises(DENIED):
        factory.rollback_assignment(ctx, assignment.id, intent)
    assert factory.get_assignment(ctx, assignment.id).version_id == second.id


@pytest.mark.asyncio
@pytest.mark.parametrize("table,field", [("agent_versions", "system_prompt"), ("agent_versions", "payload_hash"),
    ("bench_evaluations", "details_json"), ("bench_evaluations", "provenance_json"), ("approvals", "attestation"),
    ("approvals", "payload_hash"), ("bench_baselines", "attestation"), ("bench_baselines", "details_json"),
    ("bench_comparisons", "attestation"), ("bench_comparisons", "details_json"),
    ("agent_publications", "attestation"), ("agent_publications", "details_json")])
async def test_target_evidence_tampering_blocks_rollback(lifecycle, table, field):
    db, ctx, _, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    registry = {x.version_id: x for x in factory.version_registry(ctx, bp.id)}
    target = registry[first.id]
    ids = {"agent_versions": first.id, "bench_evaluations": target.evaluation_id, "approvals": target.approval_id,
        "bench_baselines": target.baseline_id, "bench_comparisons": target.regression_comparison_id,
        "agent_publications": target.publication_id}
    with corrupt_storage(db.engine) as connection:
        connection.execute(text(f"UPDATE {table} SET {field}=:value WHERE id=:id"), {"id": ids[table], "value": "tampered"})
    with pytest.raises(DENIED):
        factory.rollback_assignment(ctx, assignment.id, intent)
    assert factory.get_assignment(ctx, assignment.id).version_id == second.id
    assert not {x.version_id: x for x in factory.version_registry(ctx, bp.id)}[first.id].rollback_eligible


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_type", [ActorType.AGENT, ActorType.SYSTEM])
async def test_only_human_can_rollback(lifecycle, actor_type):
    _, ctx, _, factory, _, _, _, assignment, intent = await publications(lifecycle)
    actor = ctx.actor.model_copy(update={"actor_type": actor_type})
    forged = bind_test_context(ctx.model_copy(update={"actor": actor}))
    with pytest.raises(PermissionDeniedError):
        factory.rollback_assignment(forged, assignment.id, intent)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["operator", "viewer", "revoked"])
async def test_membership_authority_is_required(lifecycle, role):
    db, ctx, _, factory, _, _, _, assignment, intent = await publications(lifecycle)
    with db.engine.begin() as connection:
        if role == "revoked":
            connection.execute(text("UPDATE memberships SET status='revoked'"))
        else:
            connection.execute(text("UPDATE memberships SET role=:role"), {"role": role})
    with pytest.raises(PermissionDeniedError):
        factory.rollback_assignment(ctx, assignment.id, intent)


@pytest.mark.asyncio
async def test_wrong_blueprint_and_project_and_tenant_targets_rejected(lifecycle):
    db, ctx, _, factory, _, first, _, assignment, intent = await publications(lifecycle)
    other_bp = factory.create_blueprint(ctx, "Another blueprint", "other-blueprint")
    other = factory.create_version(ctx, other_bp.id, "1.0.0", "Follow research safety.", "mock-fast")
    from database.repositories.organization_repo import OrganizationRepository
    with db.session() as session:
        repo = OrganizationRepository(session)
        repo.create_organization("other-org", "Other", "other")
        repo.create_project(ctx, "other-project", "Other", "other")
    with pytest.raises(TenantIsolationError):
        factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update={"target_version_id": other.id}))
    for field in ("project_id", "organization_id"):
        with db.engine.begin() as connection:
            # Deliberate storage attack; target blueprint scope must reject it.
            connection.execute(text(f"UPDATE agent_blueprints SET {field}=:scope WHERE id=:id"),
                {"scope": "other-project" if field == "project_id" else "other-org", "id": other_bp.id})
        with pytest.raises(TenantIsolationError):
            factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update={"target_version_id": other.id}))
        with db.engine.begin() as connection:
            connection.execute(text(f"UPDATE agent_blueprints SET {field}=:scope WHERE id=:id"), {"scope": getattr(ctx, field), "id": other_bp.id})


@pytest.mark.asyncio
async def test_stale_cas_and_idempotency_conflict_do_not_create_history(lifecycle):
    db, ctx, _, factory, _, first, second, assignment, intent = await publications(lifecycle)
    for update in ({"expected_current_version_id": first.id}, {"expected_transition_id": "stale-activation"}):
        with pytest.raises(InvalidStateTransitionError):
            factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update=update))
    committed = factory.rollback_assignment(ctx, assignment.id, intent)
    for update in ({"reason": "A different governance reason."}, {"target_version_id": second.id}):
        with pytest.raises(IdempotencyConflictError):
            factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update=update))
    assert factory.rollback_assignment(ctx, assignment.id, intent).transition_id == committed.transition_id
    with db.session() as session:
        assert session.query(AssignmentTransitionModel).filter_by(assignment_id=assignment.id).count() == 2


@pytest.mark.asyncio
async def test_repository_and_orm_cannot_activate_arbitrary_version(lifecycle):
    db, ctx, _, factory, bp, first, _, assignment, intent = await publications(lifecycle)
    draft = factory.create_version(ctx, bp.id, "3.0.0", "Draft configuration.", "mock-fast")
    with db.session(write=True) as session:
        with pytest.raises(DENIED):
            AgentActivationRepository(session, db.evidence_signer).rollback(ctx, assignment.id,
                intent.model_copy(update={"target_version_id": draft.id}))
        with pytest.raises(DENIED):
            repo = AgentActivationRepository(session, db.evidence_signer)
            repo.append(ctx, session.get(AgentAssignmentModel, assignment.id), draft.id, "initial", "Forged activation.",
                {"publication": {"publication_id": "fake"}})
        with pytest.raises(InvalidStateTransitionError):
            AgentActivationRepository(session, db.evidence_signer).record_publication(ctx, first.id,
                session.query(AgentPublicationModel).filter_by(version_id=first.id).one().id)
    with pytest.raises(VersionIntegrityError):
        with db.session(write=True) as session:
            session.get(AgentAssignmentModel, assignment.id).version_id = draft.id
            session.flush()
    # Raw SQL pointer replacement is rejected by history reconciliation at runtime.
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE agent_assignments SET version_id=:version WHERE id=:id"), {"version": first.id, "id": assignment.id})
    with db.session() as session:
        with pytest.raises(VersionIntegrityError):
            AgentActivationRepository(session, db.evidence_signer).history(ctx, session.get(AgentAssignmentModel, assignment.id))


@pytest.mark.asyncio
async def test_activation_and_publication_history_are_append_only(lifecycle):
    db, ctx, _, factory, _, first, _, assignment, intent = await publications(lifecycle)
    for model, change in ((AssignmentTransitionModel, lambda x: setattr(x, "details_json", "{}")),
        (AgentPublicationModel, lambda x: setattr(x, "attestation", "changed")),
        (AgentVersionModel, lambda x: setattr(x, "system_prompt", "changed"))):
        with pytest.raises(VersionIntegrityError):
            with db.session(write=True) as session:
                change(session.query(model).first())
                session.flush()
    with corrupt_storage(db.engine) as connection:
        connection.execute(text("UPDATE assignment_transitions SET details_json='{}' WHERE assignment_id=:id"), {"id": assignment.id})
    with pytest.raises(DENIED):
        factory.rollback_assignment(ctx, assignment.id, intent)


@pytest.mark.asyncio
async def test_direct_assignment_creation_cannot_use_forged_publication(lifecycle):
    db, ctx, _, factory, bp, first = lifecycle
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE agent_versions SET status='published',published_at=CURRENT_TIMESTAMP,published_by='owner' WHERE id=:id"), {"id": first.id})
    with db.session(write=True) as session:
        with pytest.raises(DENIED):
            AgentRepository(session).create_assignment(ctx, "unsafe-assignment", bp.id, first.id, "Unsafe")


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["agent_version_id", "agent_payload_hash", "assignment_id", "assignment_transition_id", "model", "assignment_attestation"])
async def test_run_identity_tampering_rejected(lifecycle, field):
    from modules.core.workflows.coordinator import RunCoordinator
    from database.repositories.run_state_repo import RunStateRepository
    db, ctx, runtime, _, _, _, _, assignment, _ = await publications(lifecycle)
    run = await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Captured version", ctx, "captured-version-request")
    with db.engine.begin() as connection:
        connection.execute(text(f"UPDATE run_states SET {field}='tampered' WHERE id=:id"), {"id": run.run_id})
    with db.session() as session:
        with pytest.raises(InvalidStateTransitionError, match="provenance"):
            RunStateRepository(session).get_run(ctx, run.run_id)
