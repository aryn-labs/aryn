"""Live hosted persistence contracts; no model/provider network requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import threading
import sqlite3

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from database.connection import DatabaseManager, create_db_engine
from database.governance_protection import HISTORY_TABLES, verify_hosted_writer
from database.repositories.bench_regression_repo import BenchRegressionRepository
from database.repositories.budget_repo import BudgetRepository
from database.repositories.exceptions import TenantIsolationError, InvalidStateTransitionError
from database.repositories.run_state_repo import RunStateRepository
from database.schema import AuthSessionModel, ExternalIdentityModel, RunStateModel
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.audit.logger import AuditLogger
from modules.core.history import HistoryUnverifiedError
from modules.core.identity.sessions import session_identity
from modules.core.usage.engine import BudgetExceededError
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.workflows.ownership import ExecutionOwnershipError
from packages.contracts.core import AuditStatus
from packages.contracts.agent import AgentVersion, VersionIntegrityError
from packages.contracts.runtime import RunRequest
from tests.integration.test_agent_registry_rollback import publications
from tests.postgresql.conftest import migrate_to

pytestmark = pytest.mark.postgresql


def concurrent(operation):
    barrier = threading.Barrier(2)
    def start():
        barrier.wait(timeout=5)
        return operation()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(start) for _ in range(2)]
        return [future.result(timeout=20) for future in futures]


def request(key="request-one", **kwargs):
    return RunRequest(prompt="Grounded research", model="mock-fast", max_tokens=128,
                      max_total_tokens=256, idempotency_key=key, **kwargs)


def test_live_migration_chain_and_roundtrip(postgres_db):
    owner = postgres_db.owner
    with owner.connect() as connection:
        assert connection.execute(text("SELECT version()")).scalar().startswith("PostgreSQL 16.")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "017_agent_editor"
    migrate_to(owner, "012_assignment_activation", downgrade=True)
    assert "auth_sessions" not in inspect(owner).get_table_names()
    migrate_to(owner, "head")
    postgres_db.grant_writer()
    verify_hosted_writer(postgres_db.db.engine)
    migrate_to(owner, "base", downgrade=True)
    assert inspect(owner).get_table_names() == ["alembic_version"]
    migrate_to(owner, "head")
    postgres_db.grant_writer()
    assert {"external_identities", "auth_sessions", "assignment_transitions", "usage_budgets"} <= set(inspect(owner).get_table_names())


def test_writer_cannot_own_or_disable_governance_guards(postgres_db):
    db = postgres_db.db
    verify_hosted_writer(db.engine)
    with pytest.raises(HistoryUnverifiedError):
        verify_hosted_writer(postgres_db.owner)
    for table in HISTORY_TABLES:
        for statement in (f"DELETE FROM {table}", f"UPDATE {table} SET id=id", f"TRUNCATE {table}",
                          f"ALTER TABLE {table} DISABLE TRIGGER ALL"):
            with pytest.raises(DBAPIError), db.engine.begin() as connection:
                connection.execute(text(statement))
    for statement in ("CREATE TABLE unauthorized (id int)", "UPDATE alembic_version SET version_num='forged'",
                      f'SET ROLE "{postgres_db.owner_name}"', "SELECT pg_read_file('/etc/passwd')"):
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(statement))


@pytest.mark.parametrize("table", HISTORY_TABLES)
@pytest.mark.asyncio
async def test_append_only_triggers_reject_owner_dml_and_truncate(hosted_lifecycle, postgres_db, table):
    db, ctx, *_ = hosted_lifecycle
    # An owner is deliberately unsupported as runtime writer; even owner DML is
    # rejected while triggers exist. Owner DDL bypass is a separate threat boundary.
    await publications(hosted_lifecycle)
    with db.session() as session:
        assert session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() > 0
    for operation in (f"TRUNCATE {table} CASCADE", f"UPDATE {table} SET id=id", f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError), postgres_db.owner.begin() as connection:
            connection.execute(text(operation))


@pytest.mark.asyncio
async def test_baseline_and_publication_use_consistent_authorization_lock_order(hosted_lifecycle, monkeypatch):
    from modules.core.approvals.engine import ApprovalRequiredError
    db, ctx, _, factory, _, version = hosted_lifecycle
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    barrier = threading.Barrier(2)
    enforce = factory.permission_engine.enforce
    def synchronized(action, context, *args, **kwargs):
        session = kwargs.get("session")
        if session is not None and action == "version:publish" and not session.info.get("authorization_probe_seen"):
            session.info["authorization_probe_seen"] = True
            barrier.wait(timeout=5)
        result = enforce(action, context, *args, **kwargs)
        if session is not None and action == "bench:accept_baseline":
            barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(factory.permission_engine, "enforce", synchronized)
    def accept():
        with db.session(write=True) as session:
            return BenchRegressionRepository(session, db.evidence_signer).accept(ctx, evaluation.evaluation_id,
                                                                               reason="Concurrent reviewed baseline.")
    def publish():
        try:
            return factory.publish_version(ctx, version.id)
        except (ApprovalRequiredError, QualityGateFailedError):
            return "review_required"
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted, published = pool.submit(accept), pool.submit(publish)
        assert accepted.result(timeout=15).generation == 1
        assert published.result(timeout=15) == "review_required"


def test_transaction_visibility_and_row_lock(hosted_lifecycle):
    db, ctx, *_ = hosted_lifecycle
    with db.session(write=True) as session:
        budget = BudgetRepository(session).get_or_create_budget(ctx)
        budget.cumulative_tokens = 10
    with db.engine.begin() as first:
        first.execute(text("SELECT id FROM usage_budgets WHERE project_id='project' FOR UPDATE"))
        first.execute(text("UPDATE usage_budgets SET cumulative_tokens=20 WHERE project_id='project'"))
        with db.engine.connect() as second:
            assert second.execute(text("SELECT cumulative_tokens FROM usage_budgets WHERE project_id='project'")).scalar() == 10
            with pytest.raises(DBAPIError):
                second.execute(text("SELECT id FROM usage_budgets WHERE project_id='project' FOR UPDATE NOWAIT"))
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT cumulative_tokens FROM usage_budgets WHERE project_id='project'")).scalar() == 20


@pytest.mark.asyncio
async def test_concurrent_publication_is_idempotent_and_atomic(hosted_lifecycle, monkeypatch):
    db, ctx, _, factory, blueprint, version = hosted_lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    from database.repositories.agent_activation_repo import AgentActivationRepository
    record = AgentActivationRepository.record_publication
    def unavailable(*args, **kwargs):
        raise RuntimeError("isolated publication failure before database commit")
    monkeypatch.setattr(AgentActivationRepository, "record_publication", unavailable)
    with pytest.raises(RuntimeError):
        factory.publish_version(ctx, version.id)
    with db.session() as session:
        assert session.execute(text("SELECT status FROM agent_versions WHERE id=:id"), {"id": version.id}).scalar() == "approved"
        assert session.execute(text("SELECT COUNT(*) FROM bench_baselines")).scalar() == 0
        assert BenchRegressionRepository(session, db.evidence_signer).current(ctx, blueprint.id) is None
    monkeypatch.setattr(AgentActivationRepository, "record_publication", record)
    results = concurrent(lambda: factory.publish_version(ctx, version.id))
    assert {value.id for value in results} == {version.id}
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM agent_publications")).scalar() == 1
        assert session.execute(text("SELECT COUNT(*) FROM bench_baselines")).scalar() == 1
        assert all(entry.rollback_eligible for entry in factory.version_registry(ctx, blueprint.id))


@pytest.mark.asyncio
async def test_concurrent_baseline_acceptance_cas(hosted_lifecycle):
    db, ctx, _, factory, blueprint, version = hosted_lifecycle
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    def accept():
        try:
            with db.session(write=True) as session:
                value = BenchRegressionRepository(session, db.evidence_signer).accept(ctx, result.evaluation_id,
                                                                                     reason="Reviewed verified evaluation.")
            return value.baseline_id
        except QualityGateFailedError:
            return "cas_denied"
    results = concurrent(accept)
    assert results.count("cas_denied") == 1
    with db.session() as session:
        current = BenchRegressionRepository(session, db.evidence_signer).current(ctx, blueprint.id)
        assert current.baseline_id in results and current.generation == 1
        assert session.execute(text("SELECT COUNT(*) FROM bench_baselines")).scalar() == 1


@pytest.mark.asyncio
async def test_concurrent_rollback_idempotency_and_stale_cas(hosted_lifecycle):
    db, ctx, _, factory, _, first, _, assignment, intent = await publications(hosted_lifecycle)
    results = concurrent(lambda: factory.rollback_assignment(ctx, assignment.id, intent))
    assert results[0] == results[1]
    assert factory.get_assignment(ctx, assignment.id).version_id == first.id
    with pytest.raises(InvalidStateTransitionError):
        factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update={"idempotency_key": "different-intent"}))
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM assignment_transitions WHERE assignment_id=:id"), {"id": assignment.id}).scalar() == 2


def test_concurrent_budget_claim_cannot_overspend(hosted_lifecycle):
    db, ctx, runtime, *_ = hosted_lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    with db.session(write=True) as session:
        budget = BudgetRepository(session).get_or_create_budget(ctx)
        budget.max_total_tokens = 256
    def claim():
        try:
            return core._claim(request(key=os.urandom(8).hex()), ctx, "direct")[0]
        except BudgetExceededError:
            return False
    assert sorted(concurrent(claim)) == [False, True]
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 256
        assert session.query(RunStateModel).count() == 1


@pytest.mark.asyncio
async def test_concurrent_run_idempotency_and_usage_settlement(hosted_lifecycle):
    db, ctx, runtime, *_ = hosted_lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    claims = concurrent(lambda: core._claim(request(), ctx, "direct"))
    assert sorted(owner for owner, _ in claims) == [False, True]
    assert claims[0][1].run_id == claims[1][1].run_id
    result = await runtime.execute_direct_turn(request(), ctx)
    results = concurrent(lambda: core._complete_dispatch(claims[0][1].run_id, result, ctx))
    assert results[0] == results[1]
    with db.session() as session:
        budget = BudgetRepository(session).get_budget(ctx)
        assert (budget.cumulative_tokens, budget.reserved_tokens) == (result.usage.total_tokens, 0)
        assert session.query(RunStateModel).count() == 1


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_missing_or_corrupt_independent_commitment_fails_closed(hosted_lifecycle, monkeypatch, tmp_path, failure):
    db, ctx, _, factory, blueprint, _ = hosted_lifecycle
    authority = db.history_commitments
    monkeypatch.setenv("ARYN_HISTORY_COMMITMENT_PATH", str(tmp_path / "other-store.sqlite3"))
    isolated = DatabaseManager(create_db_engine(db.engine.url.render_as_string(hide_password=False)))
    try:
        with pytest.raises(HistoryUnverifiedError), isolated.session() as session:
            BenchRegressionRepository(session, db.evidence_signer).current(ctx, blueprint.id)
    finally:
        isolated.engine.dispose()
    if failure == "missing":
        authority.path.unlink()
    else:
        with sqlite3.connect(authority.path) as connection:
            connection.execute("UPDATE commitment SET signature='invalid-authentication'")
    assert all(not entry.rollback_eligible for entry in factory.version_registry(ctx, blueprint.id))
    with pytest.raises(HistoryUnverifiedError), db.session() as session:
        BenchRegressionRepository(session, db.evidence_signer).current(ctx, blueprint.id)


@pytest.mark.parametrize("missing", ["ARYN_HISTORY_COMMITMENT_PATH", "ARYN_EVIDENCE_SECRET"])
def test_hosted_authority_configuration_cannot_fallback(hosted_lifecycle, monkeypatch, missing):
    db, *_ = hosted_lifecycle
    monkeypatch.delenv(missing)
    fresh = DatabaseManager(create_db_engine(db.engine.url.render_as_string(hide_password=False)))
    try:
        with pytest.raises((HistoryUnverifiedError, ValueError)):
            _ = fresh.history_commitments
    finally:
        fresh.engine.dispose()


@pytest.mark.asyncio
async def test_replayed_assignment_pointer_blocks_core_run_and_rollback(hosted_lifecycle):
    db, ctx, runtime, factory, _, first, _, assignment, intent = await publications(hosted_lifecycle)
    rolled = factory.rollback_assignment(ctx, assignment.id, intent)
    with db.session(write=True) as session:
        prior = session.execute(text("SELECT id,to_version_id FROM assignment_transitions WHERE assignment_id=:id AND generation=1"),
                                {"id": assignment.id}).one()
        session.execute(text("UPDATE agent_assignments SET version_id=:version,current_transition_id=:transition WHERE id=:id"),
                        {"version": prior.to_version_id, "transition": prior.id, "id": assignment.id})
    calls = len(runtime.requests)
    with pytest.raises(VersionIntegrityError, match="Assignment pointer differs"):
        await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Replay must not dispatch", ctx, "replay-request")
    with pytest.raises(VersionIntegrityError, match="Assignment pointer differs"):
        factory.rollback_assignment(ctx, assignment.id, intent.model_copy(update={"expected_current_version_id": first.id,
                                    "expected_transition_id": rolled.transition_id, "idempotency_key": "replayed-history"}))
    assert len(runtime.requests) == calls
    with db.session() as session:
        from database.repositories.agent_repo import AgentRepository
        assert AgentVersion.from_stored(AgentRepository(session).get_version(ctx, first.id)).payload_hash == first.payload_hash


@pytest.mark.asyncio
async def test_populated_auth_migration_roundtrip_preserves_governance_and_runs(hosted_lifecycle, postgres_db):
    db, ctx, runtime, factory, blueprint, _, second, assignment, _ = await publications(hosted_lifecycle)
    result = await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Preserve captured provenance", ctx, "migration-run")
    with db.session() as session:
        receipts = {table: session.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() for table in HISTORY_TABLES}
        baseline = BenchRegressionRepository(session, db.evidence_signer).current(ctx, blueprint.id)
    db.engine.dispose()  # Deployment requires old binaries/authority to stop before DDL.
    migrate_to(postgres_db.owner, "014_execution_authority", downgrade=True)
    migrate_to(postgres_db.owner, "head")
    postgres_db.grant_writer()
    restored = DatabaseManager(create_db_engine(db.engine.url.render_as_string(hide_password=False)))
    try:
        with restored.session() as session:
            assert {table: session.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() for table in HISTORY_TABLES} == receipts
            assert BenchRegressionRepository(session, restored.evidence_signer).current(ctx, blueprint.id) == baseline
            run = RunStateRepository(session).get_run(ctx, result.run_id)
            assert run.agent_version_id == second.id and run.execution_attestation and run.assignment_attestation
            assert session.query(AuthSessionModel).count() == 0
    finally:
        restored.engine.dispose()


def test_second_authority_rejected_by_live_advisory_lock(hosted_lifecycle, tmp_path):
    db, _, runtime, *_ = hosted_lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    code = """import os
from database.connection import create_db_engine
from modules.core.workflows.ownership import ExecutionAuthority, ExecutionOwnershipError
engine = create_db_engine(os.environ['ARYN_TEST_WRITER_URL'])
try:
    ExecutionAuthority.for_engine(engine)
except ExecutionOwnershipError:
    print('SECOND_AUTHORITY_DENIED')
else:
    raise AssertionError('unsafe authority accepted')
finally:
    engine.dispose()
"""
    env = {**os.environ, "ARYN_TEST_WRITER_URL": db.engine.url.render_as_string(hide_password=False),
           # A separate path avoids relying on the OS lock; PostgreSQL must deny.
           "ARYN_HISTORY_COMMITMENT_PATH": str(tmp_path / "other-host.sqlite3")}
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, "Child authority probe failed; inspect isolated diagnostics."
    assert "SECOND_AUTHORITY_DENIED" in result.stdout
    core.authority.assert_valid()


@pytest.mark.asyncio
async def test_lost_postgresql_owner_fences_completion_and_recovers_unknown(hosted_lifecycle, postgres_db):
    db, ctx, runtime, *_ = hosted_lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    owner, claimed = core._claim(request(), ctx, "async")
    assert owner
    with postgres_db.admin.connect() as connection:
        assert connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": core.authority.backend_pid}).scalar()
    with pytest.raises(ExecutionOwnershipError):
        core._complete_dispatch(claimed.run_id, await runtime.execute_direct_turn(request(), ctx), ctx)
    old_id = core.authority.owner_id
    db.engine.dispose()  # A fenced engine cannot silently reacquire; restart uses a new engine.
    restarted = DatabaseManager(create_db_engine(db.engine.url.render_as_string(hide_password=False)))
    replacement = RunCoordinator(runtime, db_manager=restarted)
    assert replacement.authority.owner_id != old_id
    recovered = replacement.recover_in_flight_runs(ctx)
    assert recovered == [{"run_id": claimed.run_id, "previous_status": "started", "status": "outcome_unknown",
                          "runtime_outcome": "unknown", "cancellation_confirmed": False}]
    with restarted.session() as session:
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 256
        assert RunStateRepository(session).get_run(ctx, claimed.run_id).status == "outcome_unknown"
    restarted.engine.dispose()


def test_authenticated_audit_persistence_and_tenant_isolation(hosted_lifecycle):
    db, ctx, *_ = hosted_lifecycle
    log = AuditLogger(db)
    event = log.record("postgresql.audit", ctx, "resource", AuditStatus.ALLOWED,
                       {"prompt": "api_key=synthetic-secret"}, causation_id="verified-cause")
    persisted = log.get_events_for_correlation(ctx.correlation_id, ctx)
    current = next(item for item in persisted if item.event_id == event.event_id)
    assert db.evidence_signer.verify("audit_event", current.authenticated_payload(), current.attestation)
    other = ctx.model_copy(update={"organization_id": "other", "project_id": "other"})
    assert log.get_events_for_correlation(ctx.correlation_id, other) == []


def test_authentication_session_persistence_revocation_and_scope(hosted_lifecycle):
    db, ctx, *_ = hosted_lifecycle
    with db.session(write=True) as session:
        session.add(ExternalIdentityModel(id="external", issuer="https://identity.example", subject="stable-subject",
                                         actor_id="owner", organization_id="org", status="active"))
        session.flush()
        session.add(AuthSessionModel(token_hash="a" * 64, identity_id="external", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    with db.session(write=True) as session:
        identity = session_identity(session, "a" * 64)
        assert identity.actor_id == ctx.actor.actor_id and identity.organization_id == ctx.organization_id
        session.get(AuthSessionModel, "a" * 64).revoked_at = datetime.now(timezone.utc)
    with db.session() as session:
        assert session_identity(session, "a" * 64) is None
        assert session_identity(session, "b" * 64) is None
        with pytest.raises(TenantIsolationError):
            from database.repositories.agent_repo import AgentRepository
            AgentRepository(session).get_blueprint(ctx.model_copy(update={"project_id": "other"}), hosted_lifecycle[4].id)
