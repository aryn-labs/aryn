"""Count actual adapter dispatches while a duplicate request is in flight."""

import asyncio

import pytest
from sqlalchemy import text

from database.repositories.run_state_repo import RunStateRepository
from modules.core.workflows.coordinator import (
    IdempotencyConflictError,
    RunCoordinator,
    RunInProgressError,
)
from packages.contracts.runtime import RunRequest, RunResult, RunStatus


@pytest.mark.asyncio
async def test_concurrent_direct_requests_dispatch_runtime_once(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    execute = runtime.execute_direct_turn
    async def slow(request, context):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return await execute(request, context)
    runtime.execute_direct_turn = slow
    request = RunRequest(prompt="Research", model="mock-fast", idempotency_key="same-key")
    first = asyncio.create_task(RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(request, ctx))
    await asyncio.wait_for(entered.wait(), 3)
    second = asyncio.create_task(RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(request, ctx))
    await asyncio.sleep(0.05)
    release.set()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert calls == 1
    assert any(isinstance(value, RunResult) and value.status == RunStatus.COMPLETED for value in outcomes)
    assert any(isinstance(value, RunInProgressError) for value in outcomes)
    with db.session() as s:
        assert s.execute(text("SELECT COUNT(*) FROM run_states WHERE idempotency_key='same-key'")).scalar() == 1
        assert s.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
async def test_same_key_with_different_configuration_is_a_conflict(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    coordinator = RunCoordinator(runtime, db_manager=db)
    request = RunRequest(prompt="Research", model="mock-fast", idempotency_key="same-key")
    await coordinator.execute_managed_direct_turn(request, ctx)
    with pytest.raises(IdempotencyConflictError):
        await coordinator.execute_managed_direct_turn(request.model_copy(update={"system_instructions": "Changed"}), ctx)
    assert len(runtime.requests) == 1


@pytest.mark.asyncio
async def test_failed_timeout_retry_does_not_dispatch_again(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    calls = 0
    async def timeout(request, context):
        nonlocal calls
        calls += 1
        raise TimeoutError("Runtime outcome is unknown")
    runtime.execute_direct_turn = timeout
    coordinator = RunCoordinator(runtime, db_manager=db)
    request = RunRequest(prompt="Research", model="mock-fast", idempotency_key="timeout-key")
    with pytest.raises(TimeoutError):
        await coordinator.execute_managed_direct_turn(request, ctx)
    try:
        await coordinator.execute_managed_direct_turn(request, ctx)
    except RuntimeError:
        pass
    assert calls == 1


@pytest.mark.asyncio
async def test_async_claim_is_persisted_before_runtime_start_and_shared(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def slow_start(request, context):
        nonlocal calls
        calls += 1
        with db.session() as s:
            assert RunStateRepository(s).get_run_by_idempotency_key(ctx, request.idempotency_key).status == "started"
        entered.set()
        await release.wait()
        return "runtime-id"
    runtime.start_run = slow_start
    request = RunRequest(prompt="Research", model="mock-fast", idempotency_key="async-key")
    coordinator = RunCoordinator(runtime, db_manager=db)
    first = asyncio.create_task(coordinator.start_managed_run(request, ctx))
    await asyncio.wait_for(entered.wait(), 3)
    duplicate_id = await RunCoordinator(runtime, db_manager=db).start_managed_run(request, ctx)
    release.set()
    assert await first == duplicate_id
    assert duplicate_id != "runtime-id"
    assert calls == 1
    with db.session() as s:
        assert RunStateRepository(s).get_run(ctx, duplicate_id).runtime_run_id == "runtime-id"


@pytest.mark.asyncio
async def test_cancelled_caller_is_failed_and_retry_is_cached(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    entered, hold = asyncio.Event(), asyncio.Event()
    calls = 0
    async def interrupted(request, context):
        nonlocal calls
        calls += 1
        entered.set()
        await hold.wait()
    runtime.execute_direct_turn = interrupted
    request = RunRequest(prompt="Research", model="mock-fast", idempotency_key="crash-key")
    coordinator = RunCoordinator(runtime, db_manager=db)
    task = asyncio.create_task(coordinator.execute_managed_direct_turn(request, ctx))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = await RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(request, ctx)
    assert result.status == RunStatus.FAILED
    assert calls == 1


@pytest.mark.parametrize("lifecycle", ["metadata", "migrations"], indirect=True)
def test_threaded_claim_across_connections_dispatches_once(lifecycle):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    db, ctx, runtime, factory, bp, version = lifecycle
    barrier = threading.Barrier(8)
    lock = threading.Lock()
    calls = 0
    execute = runtime.execute_direct_turn
    async def slow(request, context):
        nonlocal calls
        with lock:
            calls += 1
        await asyncio.sleep(0.2)
        return await execute(request, context)
    runtime.execute_direct_turn = slow
    request = RunRequest(prompt="Research", model="mock-fast", idempotency_key="thread-key")
    def invoke(_):
        barrier.wait(timeout=5)
        try:
            return asyncio.run(RunCoordinator(runtime, db_manager=db).execute_managed_direct_turn(request, ctx))
        except RunInProgressError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(invoke, range(8)))
    assert calls == 1
    ids = {x.run_id for x in outcomes}
    assert len(ids) == 1
    with db.session() as s:
        assert s.execute(text("SELECT cumulative_tokens FROM usage_budgets")).scalar() == 50


@pytest.mark.asyncio
async def test_unique_runs_and_atomic_usage_for_different_requests(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    coordinator = RunCoordinator(runtime, db_manager=db)
    results = await asyncio.gather(*[
        coordinator.execute_managed_direct_turn(RunRequest(prompt="Research", model="mock-fast", idempotency_key=f"key-{i}"), ctx)
        for i in range(5)
    ])
    assert len({r.run_id for r in results}) == 5
    assert len(runtime.requests) == 5
    with db.session() as s:
        assert s.execute(text("SELECT cumulative_tokens FROM usage_budgets")).scalar() == 250
