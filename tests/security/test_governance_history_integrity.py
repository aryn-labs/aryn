"""Freshness attacks cannot replace independently committed governance state."""
import datetime
import json
import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DatabaseError

from database.connection import DatabaseManager, create_db_engine
from database.governance_protection import HISTORY_TABLES
from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.audit_repo import AuditRepository
from database.schema import AgentAssignmentModel, AuditEventModel, AssignmentTransitionModel
from modules.core.audit.logger import AuditLogger
from modules.core.history import HistoryUnverifiedError, head_key
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.permissions.engine import PermissionDeniedError
from modules.bench.quality_gate import QualityGateFailedError
from packages.contracts.core import AuditStatus
from tests.integration.test_agent_registry_rollback import publications
from tests.storage_attacks import corrupt_storage


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
@pytest.mark.parametrize("attack", ["last_activation", "all_activations", "last_baseline", "publication", "replay_receipt"])
async def test_deleted_or_replayed_history_fails_closed(lifecycle, attack):
    db, ctx, runtime, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    old_pointer = assignment.current_transition_id
    if attack in {"last_activation", "replay_receipt"}:
        factory.rollback_assignment(ctx, assignment.id, intent)
    # Bypass only DB DDL guards, modeling corruption/restore of the application
    # database while independent commitment and signer remain protected.
    with corrupt_storage(db.engine) as connection:
        if attack in {"last_activation", "replay_receipt"}:
            connection.execute(text("DELETE FROM assignment_transitions WHERE assignment_id=:id AND generation=2"), {"id": assignment.id})
            connection.execute(text("UPDATE agent_assignments SET version_id=:v,current_transition_id=:t WHERE id=:id"),
                {"id": assignment.id, "v": second.id, "t": old_pointer})
        elif attack == "all_activations":
            connection.execute(text("DELETE FROM assignment_transitions WHERE assignment_id=:id"), {"id": assignment.id})
            connection.execute(text("UPDATE agent_assignments SET current_transition_id=NULL,activation_origin='legacy' WHERE id=:id"), {"id": assignment.id})
        elif attack == "last_baseline":
            prior = connection.execute(text("SELECT id FROM bench_baselines WHERE blueprint_id=:id AND generation=1"), {"id": bp.id}).scalar_one()
            connection.execute(text("DELETE FROM bench_baselines WHERE blueprint_id=:id AND generation=2"), {"id": bp.id})
            connection.execute(text("UPDATE agent_blueprints SET bench_baseline_id=:prior WHERE id=:id"), {"id": bp.id, "prior": prior})
        else:
            connection.execute(text("DELETE FROM agent_publications WHERE version_id=:id"), {"id": second.id})
            # Mutable dates/status never establish legacy eligibility.
            connection.execute(text("UPDATE agent_versions SET published_at='2001-01-01',published_by='owner' WHERE id=:id"), {"id": second.id})
    committed = db.history_commitments.read()
    if attack == "replay_receipt":
        assert committed["heads"][head_key("assignment", ctx, assignment.id)]["generation"] == 2
    requests = len(runtime.requests)
    with pytest.raises((ValueError, QualityGateFailedError)):
        factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update={"expected_transition_id": None if attack == "all_activations" else old_pointer}))
    with pytest.raises((ValueError, QualityGateFailedError)):
        await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Must not dispatch", ctx, "history-attack-run")
    assert len(runtime.requests) == requests
    if attack in {"last_baseline", "publication"}:
        assert not {x.version_id: x for x in factory.version_registry(ctx, bp.id)}[second.id].rollback_eligible
    if attack == "last_baseline":
        assert all(not entry.current_baseline for entry in factory.version_registry(ctx, bp.id))
        third = factory.create_version(ctx, bp.id, "3.0.0", "Follow research safety guidelines.", "mock-fast")
        await factory.evaluate_version_with_bench(ctx, third.id)
        with pytest.raises(QualityGateFailedError):
            factory.approve_version(ctx, third.id)
        with pytest.raises(QualityGateFailedError):
            factory.publish_version(ctx, third.id)
    assert {x.version_id for x in factory.version_registry(ctx, bp.id)} == ({first.id, second.id, third.id} if attack == "last_baseline" else {first.id, second.id})


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("published_at", "2000-01-01"), ("published_by", "intruder")])
async def test_publication_metadata_is_bound_to_receipt(lifecycle, field, value):
    db, ctx, _, factory, bp, _, second, assignment, intent = await publications(lifecycle)
    with db.engine.begin() as connection:
        connection.execute(text(f"UPDATE agent_versions SET {field}=:value WHERE id=:id"), {"id": second.id, "value": value})
    assert not {x.version_id: x for x in factory.version_registry(ctx, bp.id)}[second.id].rollback_eligible
    with db.session() as session:
        with pytest.raises((ValueError, PermissionDeniedError)):
            AgentActivationRepository(session, db.evidence_signer).known_good(ctx, second.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["organization_id", "project_id"])
async def test_signed_history_cannot_be_substituted_across_scope(lifecycle, scope):
    db, ctx, _, factory, bp, first, second, assignment, _ = await publications(lifecycle)
    from database.repositories.organization_repo import OrganizationRepository
    from tests.conftest import bind_test_context
    foreign = ctx.model_copy(deep=True)
    foreign.project_id = foreign.actor.project_id = "foreign-project"
    if scope == "organization_id":
        foreign.organization_id = foreign.actor.organization_id = "foreign-org"
    foreign = bind_test_context(foreign)
    with db.session() as session:
        repo = OrganizationRepository(session)
        if scope == "organization_id":
            repo.create_organization("foreign-org", "Foreign", "foreign")
            repo.add_member("foreign-org", "owner", "admin")
        repo.create_project(foreign, "foreign-project", "Foreign", "foreign")
    source_bp = factory.create_blueprint(foreign, "Foreign blueprint", "foreign-blueprint")
    source = factory.create_version(foreign, source_bp.id, "1.0.0", "Follow research safety guidelines.", "mock-fast")
    await factory.evaluate_version_with_bench(foreign, source.id)
    factory.approve_version(foreign, source.id)
    factory.publish_version(foreign, source.id)
    other = factory.assign_agent(foreign, source_bp.id, source.id, "Other assignment")
    with corrupt_storage(db.engine) as connection:
        details, signature = connection.execute(text("SELECT details_json,attestation FROM assignment_transitions WHERE assignment_id=:id"), {"id": other.id}).one()
        connection.execute(text("UPDATE assignment_transitions SET details_json=:details,attestation=:signature WHERE assignment_id=:id"),
            {"id": assignment.id, "details": details, "signature": signature})
    with db.session() as session:
        with pytest.raises(ValueError):
            AgentActivationRepository(session, db.evidence_signer).history(ctx, session.get(AgentAssignmentModel, assignment.id))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_store", "missing_state", "corrupt_head", "missing_head", "pending"])
async def test_commitment_failure_blocks_run_rollback_and_promotion(lifecycle, failure):
    db, ctx, runtime, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    third = factory.create_version(ctx, bp.id, "3.0.0", "Follow research safety guidelines.", "mock-fast")
    await factory.evaluate_version_with_bench(ctx, third.id)
    store = db.history_commitments
    if failure == "missing_store":
        store.path.unlink()
    elif failure == "pending":
        store.prepare({}, {})
    else:
        # Simulated independent storage damage, not a claimed hostile host proof.
        with sqlite3.connect(store.path) as connection:
            if failure == "missing_state":
                connection.execute("DELETE FROM commitment")
            else:
                document = json.loads(connection.execute("SELECT document FROM commitment").fetchone()[0])
                key = head_key("assignment", ctx, assignment.id)
                if failure == "missing_head":
                    del document["heads"][key]
                else:
                    document["heads"][key]["generation"] = 0
                connection.execute("UPDATE commitment SET document=?", (json.dumps(document),))
    with pytest.raises(ValueError):
        factory.rollback_assignment(ctx, assignment.id, intent)
    with pytest.raises(ValueError):
        await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "No dispatch", ctx, "missing-head-run")
    with pytest.raises((ValueError, QualityGateFailedError)):
        factory.approve_version(ctx, third.id)
    assert factory.get_assignment(ctx, assignment.id).version_id == second.id
    assert all(not entry.rollback_eligible for entry in factory.version_registry(ctx, bp.id))
    assert len(runtime.requests) == 12  # Three real isolated Bench suites, no assigned execution.
    if failure == "missing_store":
        reopened = DatabaseManager(create_db_engine(str(db.engine.url)))
        with pytest.raises(HistoryUnverifiedError):
            reopened.history_commitments
        reopened.engine.dispose()


@pytest.mark.parametrize("field,value", [("actor_type", "system"), ("schema_version", "1.0.0"),
    ("causation_id", "forged-cause"), ("occurred_at", "2000-01-01 00:00:00"),
    ("event_id", "forged-event"), ("status", "failed"), ("redacted_payload_json", "{}")])
def test_authenticated_audit_binds_authority_fields_after_persistence(lifecycle, field, value):
    db, ctx, _, _, _, _ = lifecycle
    event = AuditLogger(db).record("governance.test", ctx, "resource", AuditStatus.COMPLETED,
        {"api_key": "never persist", "data": "safe"}, causation_id="actual-cause")
    with db.session() as session:
        row = session.get(AuditEventModel, event.event_id)
        assert AuditRepository(session).verify_authenticated_event(row)
        assert json.loads(row.redacted_payload_json)["api_key"] == "[REDACTED]"
        assert AuditRepository.contract(row).occurred_at.endswith("+00:00")
    with corrupt_storage(db.engine) as connection:
        connection.execute(text(f"UPDATE audit_events SET {field}=:value WHERE id=:id"), {"id": event.event_id, "value": value})
    with db.session() as session:
        assert not AuditRepository(session).verify_authenticated_event(session.get(AuditEventModel, event.event_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
@pytest.mark.parametrize("action", ["UPDATE", "DELETE", "REPLACE"])
async def test_raw_sql_cannot_rewrite_or_delete_governance_evidence(lifecycle, action):
    db, *_ = await publications(lifecycle)
    for table in HISTORY_TABLES:
        with pytest.raises(IntegrityError, match="append-only"):
            with db.engine.begin() as connection:
                statement = (f"UPDATE {table} SET id=id" if action == "UPDATE" else
                    f"DELETE FROM {table}" if action == "DELETE" else f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}")
                connection.execute(text(statement))


@pytest.mark.asyncio
async def test_committed_heads_survive_restart_and_audit_timezone_roundtrip(lifecycle):
    db, ctx, runtime, factory, bp, _, second, assignment, intent = await publications(lifecycle)
    reopened = DatabaseManager(create_db_engine(str(db.engine.url)))
    with reopened.session() as session:
        history = AgentActivationRepository(session, reopened.evidence_signer).history(ctx, session.get(AgentAssignmentModel, assignment.id))
        assert len(history) == 1 and history[-1].to_version_id == second.id
    event = AuditLogger(reopened).record("governance.timezone", ctx, assignment.id, AuditStatus.ALLOWED, {"ok": True})
    with reopened.session() as session:
        row = session.get(AuditEventModel, event.event_id)
        envelope = AuditRepository.contract(row)
        utc = datetime.datetime.fromisoformat(envelope.occurred_at)
        offset = utc.astimezone(datetime.timezone(datetime.timedelta(hours=7)))
        row.occurred_at = offset
        assert AuditRepository(session).verify_authenticated_event(row)
        session.rollback()
    reopened.engine.dispose()


@pytest.mark.asyncio
async def test_failed_commit_ack_leaves_durable_uncertainty(lifecycle, monkeypatch):
    db, ctx, _, factory, _, _, second, assignment, intent = await publications(lifecycle)
    store = db.history_commitments
    def failed_ack(token):
        raise OSError("Simulated crash after DB commit before commitment finalize")
    monkeypatch.setattr(store, "finish", failed_ack)
    with pytest.raises(OSError):
        factory.rollback_assignment(ctx, assignment.id, intent)
    with pytest.raises(HistoryUnverifiedError, match="unresolved"):
        store.read()
    with pytest.raises(HistoryUnverifiedError):
        factory.rollback_assignment(ctx, assignment.id, intent)


@pytest.mark.asyncio
async def test_signed_publication_cannot_resurrect_a_deprecated_version(lifecycle):
    db, ctx, _, factory, bp, first, _, _, _ = await publications(lifecycle)
    from database.repositories.agent_repo import AgentRepository
    with db.session(write=True) as session:
        AgentRepository(session).update_version_status(ctx, first.id, "deprecated")
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE agent_versions SET status='published' WHERE id=:id"), {"id": first.id})
    assert not {x.version_id: x for x in factory.version_registry(ctx, bp.id)}[first.id].rollback_eligible


def test_weak_historical_audit_is_readable_without_authenticated_authority(lifecycle):
    db, ctx, *_ = lifecycle
    from packages.contracts.core import AuditEvent
    event = AuditEvent(event_type="historical.event", organization_id=ctx.organization_id,
        project_id=ctx.project_id, actor_id=ctx.actor.actor_id, actor_type="user",
        correlation_id=ctx.correlation_id, resource_id="historical", status=AuditStatus.COMPLETED)
    event.integrity_reference = event.calculate_integrity()
    with db.session() as session:
        AuditRepository(session).record_event(event)
    with db.session() as session:
        stored = AuditRepository(session).get_event(ctx, event.event_id)
        assert AuditRepository.contract(stored).event_type == "historical.event"
        assert not AuditRepository(session).verify_authenticated_event(stored)
        assert not stored.attestation


def test_hash_only_downgrade_of_authenticated_audit_remains_unverified(lifecycle):
    db, ctx, *_ = lifecycle
    event = AuditLogger(db).record("governance.event", ctx, "resource", AuditStatus.COMPLETED)
    weak = event.model_copy(update={"schema_version": "1.0.0", "attestation": "", "actor_type": "system"})
    with corrupt_storage(db.engine) as connection:
        connection.execute(text("UPDATE audit_events SET schema_version='1.0.0',attestation='',actor_type='system',integrity_reference=:hash WHERE id=:id"),
            {"id": event.event_id, "hash": weak.calculate_integrity()})
    with db.session() as session:
        row = session.get(AuditEventModel, event.event_id)
        assert not AuditRepository(session).verify_authenticated_event(row)


@pytest.mark.asyncio
async def test_failed_prepare_does_not_publish_partial_state(lifecycle, monkeypatch):
    db, ctx, _, factory, _, _, second, assignment, intent = await publications(lifecycle)
    def failure(*args):
        raise HistoryUnverifiedError("Independent durable store unavailable")
    monkeypatch.setattr(db.history_commitments, "prepare", failure)
    with pytest.raises(HistoryUnverifiedError):
        factory.rollback_assignment(ctx, assignment.id, intent)
    assert factory.get_assignment(ctx, assignment.id).version_id == second.id
    with db.session() as session:
        assert session.query(AssignmentTransitionModel).filter_by(assignment_id=assignment.id).count() == 1


@pytest.mark.parametrize("operation", ["attach", "vacuum", "extension"])
def test_sqlite_writer_cannot_access_independent_authority_files(lifecycle, operation):
    db, *_ = lifecycle
    store = db.history_commitments
    with pytest.raises(DatabaseError, match="authoriz"):
        with db.engine.connect() as connection:
            if operation == "attach":
                connection.exec_driver_sql("ATTACH DATABASE ? AS authority_store", (str(store.path),))
            elif operation == "vacuum":
                connection.exec_driver_sql("VACUUM INTO ?", (str(store.path.parent / "forbidden-copy.sqlite3"),))
            else:
                connection.exec_driver_sql("SELECT load_extension('forbidden-extension')")
    assert store.read()["pending"] is None
