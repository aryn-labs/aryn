"""Execution constraints, single owner fencing and cross-boundary negative evidence."""
import asyncio
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from database.connection import DatabaseManager, create_db_engine
from database.repositories.budget_repo import BudgetRepository
from database.repositories.run_state_repo import RunStateRepository
from database.schema import RunStateModel
from modules.core.audit.logger import AuditLogger
from modules.core.usage.engine import BudgetExceededError
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.workflows.ownership import ExecutionOwnershipError
from packages.contracts.core import AuditStatus
from packages.contracts.runtime import RunRequest, RunStatus, RunUsage


def request(**changes):
    return RunRequest(prompt="Research", model="mock-fast", **changes)


@pytest.mark.asyncio
async def test_deadline_unknown_retains_reservation_and_retry_is_not_dispatched(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    calls = 0
    async def blocked(req, context):
        nonlocal calls
        calls += 1
        await asyncio.sleep(10)
    runtime.execute_direct_turn = blocked
    core = RunCoordinator(runtime, db_manager=db)
    req = request(timeout_seconds=0.2, idempotency_key="deadline")
    with pytest.raises(TimeoutError):
        await core.execute_managed_direct_turn(req, ctx)
    result = await core.execute_managed_direct_turn(req, ctx)
    assert result.status == RunStatus.OUTCOME_UNKNOWN
    assert result.usage.availability == "unavailable"
    assert calls == 1
    with db.session() as session:
        budget = BudgetRepository(session).get_budget(ctx)
        assert budget.reserved_tokens == 4096 and budget.cumulative_tokens == 0


@pytest.mark.asyncio
async def test_usage_limit_violation_is_durable_failure_not_success(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    execute = runtime.execute_direct_turn
    async def excessive(req, context):
        result = await execute(req, context)
        result.usage = RunUsage(input_tokens=30, output_tokens=90, total_tokens=120)
        return result
    runtime.execute_direct_turn = excessive
    result = await RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(
        request(max_total_tokens=100), ctx)
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert runtime.requests[-1].max_tokens <= 100
    assert result.usage.total_tokens == 120  # Do not clamp away billed evidence.
    with db.session() as session:
        budget = BudgetRepository(session).get_budget(ctx)
        assert budget.reserved_tokens == 0 and budget.cumulative_tokens == 120


@pytest.mark.asyncio
async def test_concurrent_quota_reservations_and_idempotent_settlement(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    with db.session(write=True) as session:
        budget = BudgetRepository(session).get_or_create_budget(ctx)
        budget.max_total_tokens = 4096
    entered, release = asyncio.Event(), asyncio.Event()
    execute = runtime.execute_direct_turn
    async def blocked(req, context):
        entered.set()
        await release.wait()
        return await execute(req, context)
    runtime.execute_direct_turn = blocked
    core = RunCoordinator(runtime, db_manager=db)
    req = request(idempotency_key="quota")
    task = asyncio.create_task(core.execute_managed_direct_turn(req, ctx))
    await asyncio.wait_for(entered.wait(), 2)
    with pytest.raises(BudgetExceededError):
        await core.execute_managed_direct_turn(request(idempotency_key="another"), ctx)
    release.set()
    result = await task
    assert await core.execute_managed_direct_turn(req, ctx) == result
    assert len(runtime.requests) == 1
    with db.session() as session:
        budget = BudgetRepository(session).get_budget(ctx)
        assert budget.reserved_tokens == 0 and budget.cumulative_tokens == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.FAILED])
async def test_missing_usage_never_invents_measured_zero(lifecycle, status):
    db, ctx, runtime, *_ = lifecycle
    execute = runtime.execute_direct_turn
    async def missing(req, context):
        result = await execute(req, context)
        result.status, result.usage = status, RunUsage()
        return result
    runtime.execute_direct_turn = missing
    result = await RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(request(), ctx)
    assert result.status == (RunStatus.OUTCOME_UNKNOWN if status == RunStatus.COMPLETED else RunStatus.FAILED)
    assert result.usage.availability == "unavailable"
    with db.session() as session:
        budget = BudgetRepository(session).get_budget(ctx)
        assert budget.cumulative_tokens == 0 and budget.reserved_tokens == 4096


@pytest.mark.asyncio
async def test_confirmed_partial_failure_settles_actual_usage_once(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    runtime.status = RunStatus.FAILED
    core = RunCoordinator(runtime, db_manager=db)
    req = request(idempotency_key="partial")
    result = await core.execute_managed_direct_turn(req, ctx)
    assert result.status == RunStatus.FAILED and result.usage.total_tokens == 50
    assert await core.execute_managed_direct_turn(req, ctx) == result
    assert core._complete_dispatch(result.run_id, await runtime.execute_direct_turn(req, ctx), ctx) == result
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).cumulative_tokens == 50


@pytest.mark.asyncio
async def test_bench_factory_service_consumption_uses_core_ledger(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.passed
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).cumulative_tokens == 200
        runs = session.query(RunStateModel).all()
        assert len(runs) == 4 and all(r.usage_settled and r.reserved_tokens == 0 for r in runs)


@pytest.mark.asyncio
async def test_startup_does_not_recover_live_process_runs_or_bench(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    entered, release = asyncio.Event(), asyncio.Event()
    execute = runtime.execute_direct_turn
    async def blocked(req, context):
        entered.set()
        await release.wait()
        return await execute(req, context)
    runtime.execute_direct_turn = blocked
    core = RunCoordinator(runtime, db_manager=db)
    task = asyncio.create_task(core.execute_managed_direct_turn(request(), ctx))
    await asyncio.wait_for(entered.wait(), 2)
    second = RunCoordinator(runtime, db_manager=DatabaseManager(db.engine))
    assert second.recover_in_flight_runs() == []
    with db.session() as session:
        assert session.query(RunStateModel).one().status == "started"
    release.set()
    assert (await task).status == RunStatus.COMPLETED


def test_another_process_cannot_acquire_execution_authority(lifecycle):
    db, *_ = lifecycle
    script = """from database.connection import create_db_engine
from modules.core.workflows.ownership import ExecutionAuthority, ExecutionOwnershipError
import sys
try:
    ExecutionAuthority.for_engine(create_db_engine(sys.argv[1]))
except ExecutionOwnershipError:
    print('denied')
else:
    raise AssertionError('second authority acquired lock')
"""
    completed = subprocess.run([sys.executable, "-c", script, str(db.engine.url)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0 and completed.stdout.strip() == "denied", completed.stderr


@pytest.mark.asyncio
async def test_restart_fences_stale_completion_and_recovers_unknown(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    run_id = await core.start_managed_run(request(), ctx)
    db.engine.dispose()  # Releases the actual OS authority, models process shutdown.
    new = DatabaseManager(create_db_engine(str(db.engine.url)))
    restarted = RunCoordinator(runtime, db_manager=new)
    recovery = restarted.recover_in_flight_runs(ctx)
    assert recovery[0]["run_id"] == run_id and recovery[0]["status"] == "outcome_unknown"
    with pytest.raises(ExecutionOwnershipError):
        core._complete_dispatch(run_id, await runtime.execute_direct_turn(request(), ctx), ctx)
    with new.session() as session:
        assert RunStateRepository(session).get_run(ctx, run_id).status == "outcome_unknown"
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 4096
    new.engine.dispose()


def test_scoped_empty_audit_does_not_fallback_to_another_tenant(lifecycle):
    db, ctx, *_ = lifecycle
    ctx = ctx.model_copy(update={"correlation_id": "same-correlation-negative"})
    log = AuditLogger(db)
    log.record("test", ctx, "resource", AuditStatus.ALLOWED)
    other = ctx.model_copy(update={"organization_id": "other", "project_id": "other"}, deep=True)
    assert log.get_events_for_correlation(ctx.correlation_id, other) == []
    assert len(log.get_events_for_correlation(ctx.correlation_id, ctx)) == 1
    ephemeral = AuditLogger()
    ephemeral.record("test", ctx, "resource", AuditStatus.ALLOWED)
    assert ephemeral.get_events_for_correlation(ctx.correlation_id, other) == []


def test_audit_nested_content_is_fingerprint_only_and_credentials_scrubbed(lifecycle):
    db, ctx, *_ = lifecycle
    secret = "sk-synthetic-credential-for-negative-test"
    event = AuditLogger(db).record("test", ctx, "resource", AuditStatus.FAILED,
        {"prompt": secret, "nested": {"output": secret, "message": f"api_key={secret}", "authorization": secret}})
    encoded = json.dumps(event.redacted_payload)
    assert secret not in encoded and "prompt_reference" in encoded and "output_reference" in encoded
    assert event.attestation


@pytest.mark.asyncio
async def test_injected_authority_survives_missing_environment_identity(lifecycle, monkeypatch):
    from modules.core.identity.binder import TrustedIdentityBinder
    from modules.core.permissions.engine import PermissionEngine
    from modules.agent_factory.service import AgentFactoryService
    from modules.bench.runner import BenchRunner
    from database.repositories.bench_repo import BenchRepository
    db, ctx, runtime, _, bp, version = lifecycle
    binder = TrustedIdentityBinder(secret_key=b"explicit-injected-core-secret-32bytes")
    permissions = PermissionEngine(db, identity_binder=binder)
    ctx = binder.bind_context(ctx)
    monkeypatch.delenv("ARYN_IDENTITY_SECRET")
    factory = AgentFactoryService(db, BenchRunner(runtime), permission_engine=permissions)
    from packages.contracts.bench import ApprovalGraderSpec, ApprovalRequirement, evidence_hash
    from tests.bench_fixtures import create_generic_version, generic_suite, generic_scenario
    payload = evidence_hash({"operation": "trusted-injected-review"})
    factory.approval_engine.grant_approval(ctx, "test_action", "operation", payload)
    scenario = generic_scenario()
    scenario.graders.append(ApprovalGraderSpec(grader_id="human", requirement=ApprovalRequirement(
        target_type="test_action", target_id="operation", payload_hash=payload, allowed_actors=["owner"])))
    suite = generic_suite(scenarios=[scenario], scenario_ids=[scenario.scenario_id])
    db, ctx, runtime, factory, bp, version = create_generic_version((db, ctx, runtime, factory, bp, version), monkeypatch, suite)
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert result.passed and result.scenario_results[0].grader_results[-1].reason == "core_approval_verified"
    factory.approve_version(ctx, version.id)
    published = factory.publish_version(ctx, version.id)
    with db.session() as session:
        repo = BenchRepository(session, db.evidence_signer)
        assert repo.approval_authority() is factory.approval_engine
        assert repo.validate_stored(ctx, repo.get_evaluation(ctx, result.evaluation_id), published).passed


@pytest.mark.asyncio
async def test_revoked_membership_after_claim_blocks_runtime_dispatch(lifecycle):
    from modules.core.permissions.engine import PermissionDeniedError
    db, ctx, runtime, *_ = lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    availability = runtime.require_model_available
    async def revoked(model):
        await availability(model)
        with db.session(write=True) as session:
            session.execute(text("UPDATE memberships SET status='revoked'"))
    runtime.require_model_available = revoked
    with pytest.raises(PermissionDeniedError):
        await core.execute_managed_direct_turn(request(), ctx)
    assert runtime.requests == []


@pytest.mark.asyncio
async def test_async_deadline_transitions_without_polling_and_cannot_be_completed(lifecycle, monkeypatch):
    from modules.core.workflows import coordinator

    db, ctx, runtime, *_ = lifecycle
    now = datetime.datetime.now(datetime.timezone.utc)
    starting = True
    clock_offset = datetime.timedelta(0)

    class ControlledDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            current = now if starting else datetime.datetime.now(datetime.timezone.utc) + clock_offset
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    # Freeze only the coordinator's clock through claim and runtime startup.
    # The signed deadline and the actual asynchronous watchdog remain unchanged;
    # loaded-host admission must not consume this test's watchdog interval.
    monkeypatch.setattr(coordinator, "datetime", SimpleNamespace(
        datetime=ControlledDateTime, timedelta=datetime.timedelta, timezone=datetime.timezone,
    ))
    core = RunCoordinator(runtime, db_manager=db)
    run_id = await core.start_managed_run(request(timeout_seconds=0.2), ctx)
    with db.session() as session:
        row = RunStateRepository(session).get_run(ctx, run_id)
        assert row.status == "started" and row.runtime_run_id == "test_only"
        assert row.reserved_tokens == 4096
    watchdogs = tuple(core._deadline_tasks)
    assert len(watchdogs) == 1
    clock_offset = now - datetime.datetime.now(datetime.timezone.utc)
    starting = False
    # Await the real watchdog, without polling or calling _fail_dispatch.
    await asyncio.wait_for(asyncio.gather(*watchdogs), timeout=10)
    with db.session() as session:
        row = RunStateRepository(session).get_run(ctx, run_id)
        assert row.status == "outcome_unknown" and row.reserved_tokens == 4096
    before = (await core.get_managed_result(run_id, ctx)).model_dump()
    result = await runtime.execute_direct_turn(request(), ctx)
    assert core._complete_dispatch(run_id, result, ctx).model_dump() == before


@pytest.mark.asyncio
async def test_measured_cost_source_and_limits_are_durable(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    execute = runtime.execute_direct_turn
    async def with_cost(req, context):
        result = await execute(req, context)
        result.usage.cost_usd, result.usage.cost_source = 0.1, "provider_usage"
        return result
    runtime.execute_direct_turn = with_cost
    core = RunCoordinator(runtime, db_manager=db)
    req = request(max_cost_usd=0.05, idempotency_key="measured-cost")
    result = await core.execute_managed_direct_turn(req, ctx)
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert result.usage.cost_usd == 0.1 and result.usage.cost_source == "provider_usage"
    assert await core.execute_managed_direct_turn(req, ctx) == result
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).cumulative_cost_usd == 0.1


def test_project_admin_cannot_advertise_organization_governance_authority(lifecycle):
    from database.repositories.organization_repo import OrganizationRepository
    from modules.core.approvals.engine import UnauthorizedApproverError
    db, ctx, runtime, factory, *_ = lifecycle
    with db.session(write=True) as session:
        session.execute(text("UPDATE memberships SET role='operator'"))
        OrganizationRepository(session).add_project_member(ctx.project_id, ctx.actor.actor_id, "admin")
    for action in ("version:approve", "bench:accept_baseline", "agent:rollback"):
        assert not factory.permission_engine.evaluate(action, ctx, ctx.organization_id, ctx.project_id).allowed
    with pytest.raises(UnauthorizedApproverError):
        factory.approval_engine.grant_approval(ctx, "test_action", "target", "a" * 64)


def test_role_change_between_preflight_and_factory_commit_is_denied(lifecycle, monkeypatch):
    from modules.core.permissions.engine import PermissionDeniedError
    db, ctx, runtime, factory, *_ = lifecycle
    enforce = factory.permission_engine.enforce
    def revoked(action, context, *args, **kwargs):
        result = enforce(action, context, *args, **kwargs)
        if action == "run:create" and kwargs.get("session") is None:
            with db.session(write=True) as session:
                session.execute(text("UPDATE memberships SET role='viewer'"))
        return result
    monkeypatch.setattr(factory.permission_engine, "enforce", revoked)
    with pytest.raises(PermissionDeniedError):
        factory.create_blueprint(ctx, "Revoked", "revoked")
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM agent_blueprints WHERE slug='revoked'")).scalar() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["owner", "deadline", "limits", "model", "remove"])
async def test_signed_execution_claim_cannot_be_rewritten_or_downgraded(lifecycle, tamper):
    from database.repositories.exceptions import InvalidStateTransitionError
    from modules.core.permissions.engine import PermissionDeniedError
    db, ctx, runtime, *_ = lifecycle
    core = RunCoordinator(runtime, db_manager=db)
    req = request(idempotency_key="signed-claim")
    run_id = await core.start_managed_run(req, ctx)
    changes = {
        "owner": "execution_owner_id='old-owner'", "deadline": "deadline_at='2099-01-01 00:00:00'",
        "limits": "effective_limits_json='{}'", "model": "model='other-model'",
        "remove": "execution_claim_json=NULL,execution_attestation=NULL,execution_owner_id=NULL,status='completed'",
    }
    with db.session(write=True) as session:
        session.execute(text(f"UPDATE run_states SET {changes[tamper]} WHERE id=:id"), {"id": run_id})
    if tamper == "remove":
        with pytest.raises(PermissionDeniedError):
            await core.start_managed_run(req, ctx)
    else:
        with pytest.raises(InvalidStateTransitionError):
            await core.get_managed_result(run_id, ctx)
    assert runtime.requests == []


@pytest.mark.asyncio
async def test_legacy_unknown_consumption_blocks_new_budget_claim(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    with db.session(write=True) as session:
        repo = RunStateRepository(session)
        repo.create_run(ctx, "historical", "Old prompt", "mock-fast", "mock")
        repo.transition_status(ctx, "historical", "started")
    with pytest.raises(BudgetExceededError, match="reconciliation"):
        await RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(request(), ctx)
    assert runtime.requests == []
    with db.session() as session:
        assert RunStateRepository(session).get_run(ctx, "historical").status == "started"
        assert BudgetRepository(session).get_budget(ctx) is None


@pytest.mark.asyncio
async def test_immutable_agent_deadline_and_tokens_override_runtime_default(lifecycle):
    from packages.contracts.agent import AgentBudgetPolicy, AgentConstraints
    db, ctx, runtime, factory, bp, _ = lifecycle
    version = factory.create_version(ctx, bp.id, "2.0.0", "Follow research safety guidelines.", "mock-fast",
        budget_policy=AgentBudgetPolicy(timeout_seconds=1, max_tokens_per_run=512),
        constraints=AgentConstraints(max_execution_time_seconds=2))
    assert (await factory.evaluate_version_with_bench(ctx, version.id)).passed
    factory.approve_version(ctx, version.id)
    factory.publish_version(ctx, version.id)
    assignment = factory.assign_agent(ctx, bp.id, version.id, "Research")
    captured = []
    async def slow(req, context):
        captured.append(req)
        await asyncio.sleep(10)
    runtime.execute_direct_turn = slow
    with pytest.raises(TimeoutError):
        await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Research", ctx, "agent-deadline")
    assert captured[0].timeout_seconds == 1 and captured[0].max_total_tokens == 512
    assert captured[0].max_tokens < 512
    with db.session() as session:
        run = RunStateRepository(session).get_run_by_idempotency_key(ctx, "agent-deadline")
        assert run.status == "outcome_unknown" and run.reserved_tokens == 512


def test_real_process_crash_releases_lock_but_preserves_unknown_run(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    url = str(db.engine.url)
    db.engine.dispose()
    script = """from database.connection import DatabaseManager, create_db_engine
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.identity.binder import TrustedIdentityBinder
from tests.studio_runtime import IsolatedTestRuntime
from packages.contracts.runtime import RunRequest
import sys, time
db = DatabaseManager(create_db_engine(sys.argv[1]))
ctx = TrustedIdentityBinder().create_trusted_context('owner', 'org', 'project')
core = RunCoordinator(IsolatedTestRuntime(), db_manager=db)
owner, result = core._claim(RunRequest(prompt='Research', model='mock-fast'), ctx, 'direct')
print(result.run_id, flush=True)
time.sleep(60)
"""
    child = subprocess.Popen([sys.executable, "-u", "-c", script, url], cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    new = DatabaseManager(create_db_engine(url))
    try:
        # Read through a bounded thread so a regression never blocks the test suite.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(1) as pool:
            run_id = pool.submit(child.stdout.readline).result(timeout=15).strip()
        assert run_id.startswith("run_"), child.stderr.read() if child.poll() is not None else "claim not ready"
        with pytest.raises(ExecutionOwnershipError):
            RunCoordinator(runtime, db_manager=new)
        deadline = time.monotonic() + 10
        child.terminate()
        child.wait(timeout=10)
        # Windows may still reject the file lock immediately after process exit.
        # Observe actual acquisition within the original shutdown deadline; never
        # bypass a lock or add timeout-based takeover to production authority.
        while True:
            try:
                restarted = RunCoordinator(runtime, db_manager=new)
                break
            except ExecutionOwnershipError:
                remaining = deadline - time.monotonic()
                if os.name != "nt" or remaining <= 0:
                    raise
                threading.Event().wait(min(0.01, remaining))
        recovered = restarted.recover_in_flight_runs(ctx)
        assert len(recovered) == 1 and recovered[0]["run_id"] == run_id
        assert recovered[0]["status"] == "outcome_unknown" and recovered[0]["cancellation_confirmed"] is False
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        new.engine.dispose()


@pytest.mark.asyncio
async def test_organization_quota_is_shared_across_projects(lifecycle):
    from database.repositories.organization_repo import OrganizationRepository
    from tests.conftest import bind_test_context
    db, ctx, runtime, *_ = lifecycle
    other = bind_test_context(ctx.model_copy(update={"project_id": "other"}, deep=True))
    organization = ctx.model_copy(update={"project_id": "*"}, deep=True)
    with db.session(write=True) as session:
        OrganizationRepository(session).create_project(ctx, "other", "Other", "other")
        BudgetRepository(session).get_or_create_budget(organization, max_total_tokens=4096)
    entered, release = asyncio.Event(), asyncio.Event()
    execute = runtime.execute_direct_turn
    async def blocked(req, context):
        entered.set()
        await release.wait()
        return await execute(req, context)
    runtime.execute_direct_turn = blocked
    core = RunCoordinator(runtime, db_manager=db)
    task = asyncio.create_task(core.execute_managed_direct_turn(request(), ctx))
    await asyncio.wait_for(entered.wait(), 2)
    with pytest.raises(BudgetExceededError):
        await core.execute_managed_direct_turn(request(), other)
    release.set()
    assert (await task).status == RunStatus.COMPLETED
    with db.session() as session:
        assert BudgetRepository(session).get_budget(organization).cumulative_tokens == 50
        assert BudgetRepository(session).get_budget(other) is None  # Denied claim rolls back its budget insert.


@pytest.mark.asyncio
async def test_cancellation_ack_does_not_prevent_unknown_outcome(lifecycle):
    db, ctx, runtime, *_ = lifecycle
    async def start(req, context):
        return "ack-only"
    async def poll(run_id, context):
        from packages.contracts.runtime import RunResult
        return RunResult(run_id=run_id, status=RunStatus.RUNNING, model="mock-fast", created_at=0, output="")
    async def acknowledge(run_id, context):
        return True
    runtime.start_run, runtime.get_result, runtime.cancel_run = start, poll, acknowledge
    core = RunCoordinator(runtime, db_manager=db)
    run_id = await core.start_managed_run(request(timeout_seconds=30), ctx)
    assert await core.cancel_managed_run(run_id, ctx) is False
    with db.session() as session:
        assert RunStateRepository(session).get_run(ctx, run_id).status == "stopping"
    # Deterministic timeout callback after the acknowledgement; real watchdog
    # deadline timing is covered separately, without relying on loaded-host sleeps.
    core._fail_dispatch(run_id, ctx, TimeoutError())
    result = await core.get_managed_result(run_id, ctx)
    assert result.status == RunStatus.OUTCOME_UNKNOWN
    assert result.usage.availability == "unavailable"
    with db.session() as session:
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 4096


@pytest.mark.asyncio
async def test_async_result_revocation_does_not_disclose_output(lifecycle):
    from database.schema import MembershipModel
    from modules.core.permissions.engine import PermissionDeniedError
    db, ctx, runtime, *_ = lifecycle
    async def start(req, context):
        return "revoked-result"
    async def poll(run_id, context):
        from packages.contracts.runtime import RunResult
        with db.session(write=True) as session:
            session.query(MembershipModel).filter_by(user_id=ctx.actor.actor_id).one().status = "revoked"
        return RunResult(run_id=run_id, status=RunStatus.COMPLETED, model="mock-fast", output="private output", created_at=0,
            usage=RunUsage(input_tokens=10, output_tokens=20, total_tokens=30))
    runtime.start_run, runtime.get_result = start, poll
    core = RunCoordinator(runtime, db_manager=db)
    run_id = await core.start_managed_run(request(), ctx)
    with pytest.raises(PermissionDeniedError):
        await core.get_managed_result(run_id, ctx)
    with db.session() as session:
        row = RunStateRepository(session).get_run(ctx, run_id)
        assert row.status == "completed" and row.usage_settled == 1
        assert BudgetRepository(session).get_budget(ctx).cumulative_tokens == 30


@pytest.mark.asyncio
async def test_factory_bench_preflight_obeys_immutable_agent_deadline(lifecycle):
    from packages.contracts.agent import AgentBudgetPolicy
    from database.repositories.agent_repo import AgentRepository
    db, ctx, runtime, factory, bp, _ = lifecycle
    version = factory.create_version(ctx, bp.id, "3.0.0", "Follow research safety guidelines.", "mock-fast",
        budget_policy=AgentBudgetPolicy(timeout_seconds=1))
    async def blocked():
        await asyncio.sleep(10)
    runtime.capabilities = blocked
    with pytest.raises(TimeoutError):
        await factory.evaluate_version_with_bench(ctx, version.id)
    assert runtime.requests == []
    with db.session() as session:
        assert AgentRepository(session).get_version(ctx, version.id).status == "rejected"
        assert session.query(RunStateModel).count() == 0
        assert BudgetRepository(session).get_budget(ctx) is None
