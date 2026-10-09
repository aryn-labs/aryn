"""Real Core scheduling, persisted provenance and adversarial authority checks."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import text
from tests.integration.test_studio_api import studio as studio, draft, promoted, PREFIX
from tests.integration.test_workflow_execution import workflow as workflow
from tests.integration.test_intelligence_recovery import post
from modules.core.automations.service import CoreAutomations
from modules.core.automations.recurrence import instant
from packages.contracts.automation import ManualOccurrence
from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT
from database.schema import (
    RunStateModel,
    AutomationOccurrenceModel,
    AutomationDefinitionModel,
    MembershipModel,
)


def scheduled(studio, *, policy=None, kind="agent", workflow_target=None):
    client, db, runtime, app = studio
    if kind == "agent":
        bp, version = draft(client, "scheduled-" + uuid.uuid4().hex[:12])
        assignment = promoted(client, bp, version)
        target = {
            "kind": "agent",
            "id": assignment["id"],
            "version_id": version["id"],
            "payload_hash": version["payload_hash"],
            "activation_id": assignment["current_transition_id"],
        }
    else:
        definition, version = workflow_target
        target = {
            "kind": "workflow",
            "id": definition["id"],
            "version_id": version["id"],
            "payload_hash": version["digest"],
        }
    clock = [datetime.now(timezone.utc).replace(microsecond=0)]
    app.state.automations.clock = lambda: clock[0]
    body = {
        "title": "Core scheduled research",
        "target": target,
        "input": "Research safe scoped evidence.",
        "allow_remote_model": True,
        "schedule": {
            "kind": "interval",
            "timezone": "Asia/Bangkok",
            "interval_minutes": 5,
            "start_at": clock[0].isoformat(),
        },
        "policy": {"max_tokens_per_task": 4096, **(policy or {})},
    }
    definition = post(client, "/automations", body)
    return definition, body, clock


def enable(client, definition):
    post(
        client,
        f"/automations/{definition['id']}/approve",
        {
            "expected_revision": definition["revision"],
            "payload_hash": definition["payload_hash"],
            "reason": "Human review of pinned target, schedule and bounded execution policy.",
        },
    )
    return post(
        client,
        f"/automations/{definition['id']}/state",
        {"expected_revision": definition["revision"], "enabled": True},
    )


def occurrences(client, definition):
    response = client.get(PREFIX + f"/automations/{definition['id']}/occurrences")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_tick_real_claim_pinned_model_usage_and_manual_idempotency(studio):
    client, db, runtime, app = studio
    definition, _, clock = scheduled(studio)
    definition = enable(client, definition)
    count = len(runtime.requests)
    clock[0] = instant(definition["next_run_at"])
    asyncio.run(app.state.automations.tick())
    rows = occurrences(client, definition)
    assert len(rows) == 1 and rows[0]["status"] == "completed", rows
    with db.session() as session:
        run = session.get(RunStateModel, rows[0]["run_id"])
        result = app.state.coordinator.stored_result(run)
        assert result.execution_claim_verified and result.assignment_provenance_verified
        assert (
            result.agent_version_id
            == definition["configuration"]["target"]["version_id"]
        )
        assert (
            result.assignment_transition_id
            == definition["configuration"]["target"]["activation_id"]
        )
        assert (
            result.execution_provenance["automation"]["occurrence_id"] == rows[0]["id"]
        )
        assert result.usage.availability == "measured" and result.usage.total_tokens > 0
    asyncio.run(app.state.automations.tick())
    clock[0] -= timedelta(hours=1)
    asyncio.run(app.state.automations.tick())
    assert len(runtime.requests) == count + 1
    body = {"expected_revision": 1, "idempotency_key": "human-override"}
    first = post(client, f"/automations/{definition['id']}/run", body)
    repeated = post(client, f"/automations/{definition['id']}/run", body)
    assert first == repeated and first["status"] == "completed"
    assert len(runtime.requests) == count + 2
    assert (
        client.get(PREFIX + f"/automations/{definition['id']}").json()[
            "last_occurrence_id"
        ]
        == first["id"]
    )


def test_division_assignment_preserves_scope_and_rejects_foreign_division(studio):
    from database.repositories.organization_repo import OrganizationRepository

    client, db, _, app = studio
    definition, _, _ = scheduled(studio)
    division = post(
        client,
        "/divisions",
        {"name": "Scoped evidence team", "slug": "scoped-evidence-team"},
    )
    with db.session(write=True) as session:
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
        OrganizationRepository(session).create_project(
            ctx, "proj_division_other", "Other project", "division-other"
        )
    foreign = client.post(
        "/api/projects/proj_division_other/divisions",
        json={"name": "Other team", "slug": "other-team"},
    )
    assert foreign.status_code == 201, foreign.text
    version = definition["configuration"]["target"]["version_id"]
    lifecycle = client.get(PREFIX + f"/lifecycle?version_id={version}").json()
    blueprint = next(item for item in lifecycle["versions"] if item["id"] == version)[
        "blueprint_id"
    ]
    body = {
        "blueprint_id": blueprint,
        "version_id": version,
        "role_name": "Scoped division researcher",
        "division_id": division["id"],
    }
    created = post(client, "/assignments", body)
    assert created["division_id"] == division["id"]
    for invalid in ("division_absent", foreign.json()["id"]):
        denied = client.post(
            PREFIX + "/assignments",
            json={
                **body,
                "role_name": "Foreign division researcher",
                "division_id": invalid,
            },
        )
        assert denied.status_code == 404, denied.text


@pytest.mark.parametrize(
    "missed,expected", [("skip", ["skipped"] * 3), ("catch_up", ["completed"] * 3)]
)
def test_restart_clock_jump_bounded_missed_policy(studio, missed, expected):
    client, _, runtime, app = studio
    definition, _, clock = scheduled(
        studio, policy={"missed": missed, "catch_up_limit": 3}
    )
    definition = enable(client, definition)
    count = len(runtime.requests)
    clock[0] += timedelta(days=60, seconds=120)
    asyncio.run(app.state.automations.tick())
    rows = occurrences(client, definition)
    assert sorted(r["status"] for r in rows) == expected
    assert len(runtime.requests) == count + (3 if missed == "catch_up" else 0)
    events = client.get(
        PREFIX + f"/automations/{definition['id']}/events?limit=100"
    ).json()["items"]
    assert any(e["event"] == "missed.coalesced" for e in events)
    asyncio.run(app.state.automations.tick())
    assert len(occurrences(client, definition)) == 3


def test_concurrent_tick_and_manual_delivery_admit_once(studio):
    client, _, runtime, app = studio
    definition, _, clock = scheduled(studio)
    definition = enable(client, definition)
    clock[0] = instant(definition["next_run_at"])
    second = CoreAutomations(app.state.coordinator, clock=lambda: clock[0])
    count = len(runtime.requests)

    async def contend():
        entered, release = asyncio.Event(), asyncio.Event()

        async def readiness():
            entered.set()
            await release.wait()

        app.state.automations.require_runtime = readiness
        second.require_runtime = readiness
        running = asyncio.create_task(app.state.automations.tick())
        await entered.wait()
        await second.tick()
        release.set()
        await running
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
        requests = [
            ManualOccurrence(expected_revision=1, idempotency_key="same-manual")
            for _ in range(4)
        ]
        entered.clear()
        release.clear()
        manual = asyncio.create_task(second.manual(ctx, definition["id"], requests[0]))
        await entered.wait()
        results = await asyncio.gather(
            *(second.manual(ctx, definition["id"], body) for body in requests[1:])
        )
        release.set()
        results.append(await manual)
        assert len({r["id"] for r in results}) == 1

    asyncio.run(contend())
    assert len(occurrences(client, definition)) == 2
    assert len(runtime.requests) == count + 2


def test_schedule_change_invalidates_old_approval_and_paused_tick(studio):
    client, _, runtime, app = studio
    definition, body, clock = scheduled(studio)
    definition = enable(client, definition)
    changed = post(
        client,
        f"/automations/{definition['id']}",
        {**body, "input": "Different exact approved work", "expected_revision": 1},
    )
    assert (
        changed["status"] == "paused"
        and changed["payload_hash"] != definition["payload_hash"]
    )
    assert (
        client.post(
            PREFIX + f"/automations/{definition['id']}/state",
            json={"expected_revision": 2, "enabled": True},
        ).status_code
        == 409
    )
    assert (
        client.post(
            PREFIX + f"/automations/{definition['id']}/approve",
            json={
                "expected_revision": 1,
                "payload_hash": definition["payload_hash"],
                "reason": "Old approval",
            },
        ).status_code
        == 409
    )
    count = len(runtime.requests)
    clock[0] += timedelta(minutes=30, seconds=120)
    asyncio.run(app.state.automations.tick())
    assert not occurrences(client, definition) and len(runtime.requests) == count
    enable(client, changed)
    asyncio.run(app.state.automations.tick())
    assert occurrences(client, definition)[0]["status"] == "skipped"


def test_revoked_owner_pauses_without_dispatch(studio):
    client, db, runtime, app = studio
    definition, _, clock = scheduled(studio)
    definition = enable(client, definition)
    count = len(runtime.requests)
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(
            user_id=DEV_ACTOR
        ).one().status = "revoked"
    clock[0] = instant(definition["next_run_at"])
    asyncio.run(app.state.automations.tick())
    with db.session() as session:
        assert (
            session.get(AutomationDefinitionModel, definition["id"]).status == "paused"
        )
        assert session.query(AutomationOccurrenceModel).count() == 0
    assert len(runtime.requests) == count
    assert client.get(PREFIX + "/automations").status_code == 403


def test_revocation_inside_claim_rolls_back_before_runtime(studio, monkeypatch):
    client, db, runtime, app = studio
    definition, _, _ = scheduled(studio)
    enable(client, definition)
    count = len(runtime.requests)
    original = app.state.coordinator._claim
    with db.session() as session:
        prior_runs = session.query(RunStateModel).count()

    def revoked(*args, **kwargs):
        result = original(*args, **kwargs)
        kwargs["session"].query(MembershipModel).filter_by(
            user_id=DEV_ACTOR
        ).one().status = "revoked"
        kwargs["session"].flush()
        return result

    monkeypatch.setattr(app.state.coordinator, "_claim", revoked)
    result = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "revoked-at-commit"},
    )
    assert result["status"] == "blocked" and not result["run_id"]
    assert len(runtime.requests) == count
    with db.session() as session:
        assert session.query(RunStateModel).count() == prior_runs


def test_budget_denial_has_no_effect_and_daily_policy_is_real(studio):
    client, db, runtime, app = studio
    definition, configuration, _ = scheduled(studio, policy={"max_runs_per_day": 1})
    enable(client, definition)
    first = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "first"},
    )
    count = len(runtime.requests)
    second = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "second"},
    )
    assert first["status"] == "completed" and second["status"] == "blocked"
    assert (
        second["error_code"] == "automation_daily_budget"
        and len(runtime.requests) == count
    )
    # A separate schedule has its own quota, but the shared Core budget still denies.
    definition = post(
        client,
        "/automations",
        {
            **configuration,
            "title": "Separate schedule shares Core budget",
            "policy": {"max_runs_per_day": 24, "max_tokens_per_task": 4096},
        },
    )
    enable(client, definition)
    count = len(runtime.requests)
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE usage_budgets SET max_tokens_per_run=128"))
    denied = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "core-denied"},
    )
    assert (
        denied["status"] == "blocked" and denied["error_code"] == "core_budget_denied"
    )
    assert len(runtime.requests) == count


def test_readiness_backoff_retries_only_before_core_claim(studio):
    client, _, runtime, app = studio
    definition, _, clock = scheduled(
        studio, policy={"max_attempts": 2, "backoff_seconds": 60}
    )
    enable(client, definition)
    count = len(runtime.requests)
    runtime.online = False
    first = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "offline"},
    )
    assert first["status"] == "retry_wait" and first["run_id"] is None
    asyncio.run(app.state.automations.tick())
    assert occurrences(client, definition)[0]["attempts"] == 1
    runtime.online = True
    clock[0] += timedelta(seconds=61)
    asyncio.run(app.state.automations.tick())
    assert occurrences(client, definition)[0]["status"] == "completed"
    assert len(runtime.requests) == count + 1


def test_queued_previous_day_counts_against_actual_admission_day(studio):
    client, _, runtime, app = studio
    definition, _, clock = scheduled(studio, policy={"max_runs_per_day": 1})
    definition = enable(client, definition)
    scheduler = app.state.automations
    clock[0] = instant(definition["next_run_at"])
    queued = scheduler.plan(definition["id"], DEV_ORG, DEV_PROJECT)
    assert len(queued) == 1
    clock[0] += timedelta(days=1)
    admitted = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "current-day-admission"},
    )
    assert admitted["status"] == "completed"
    count = len(runtime.requests)
    asyncio.run(scheduler.dispatch(queued[0], definition))
    previous = next(
        row for row in occurrences(client, definition) if row["id"] == queued[0]
    )
    assert (
        previous["status"] == "blocked"
        and previous["error_code"] == "automation_daily_budget"
    )
    assert previous["run_id"] is None and len(runtime.requests) == count


def test_planner_locks_membership_before_definition(studio, monkeypatch):
    client, _, _, app = studio
    definition, _, clock = scheduled(studio)
    definition = enable(client, definition)
    clock[0] = instant(definition["next_run_at"])
    scheduler = app.state.automations
    enforce, verified = scheduler.permissions.enforce, scheduler._verified
    observed = []

    def checked_permission(action, ctx, *args, **kwargs):
        result = enforce(action, ctx, *args, **kwargs)
        session = kwargs.get("session")
        if (
            session is not None
            and session.info.get("write")
            and action == "version:approve"
        ):
            session.info["scheduler_membership_locked"] = True
        return result

    def checked_definition(session, cls, ctx, identifier, lock=False):
        if cls is AutomationDefinitionModel and lock:
            assert session.info.get("scheduler_membership_locked")
            observed.append(identifier)
        return verified(session, cls, ctx, identifier, lock)

    monkeypatch.setattr(scheduler.permissions, "enforce", checked_permission)
    monkeypatch.setattr(scheduler, "_verified", checked_definition)
    assert len(scheduler.plan(definition["id"], DEV_ORG, DEV_PROJECT)) == 1
    assert observed == [definition["id"]]


def test_application_lifespan_dispatches_and_stops_on_owner_loss(studio, monkeypatch):
    from fastapi import FastAPI
    from services.api.automations import register_automations
    from modules.core.workflows.ownership import ExecutionOwnershipError

    client, _, runtime, existing = studio
    definition, _, clock = scheduled(studio)
    definition = enable(client, definition)
    clock[0] = instant(definition["next_run_at"])
    application = FastAPI()
    register_automations(
        application, existing.state.coordinator, lambda *args: None, None
    )
    scheduler = application.state.automations
    scheduler.clock = lambda: clock[0]
    tick = scheduler.tick
    count = len(runtime.requests)

    async def exercise():
        finished = asyncio.Event()

        async def observed():
            await tick()
            finished.set()

        monkeypatch.setattr(scheduler, "tick", observed)
        async with application.router.lifespan_context(application):
            await asyncio.wait_for(finished.wait(), timeout=5)
            assert len(runtime.requests) == count + 1
        lost = asyncio.Event()

        async def fenced():
            lost.set()
            raise ExecutionOwnershipError("Test owner lost")

        monkeypatch.setattr(scheduler, "tick", fenced)
        async with application.router.lifespan_context(application):
            await asyncio.wait_for(lost.wait(), timeout=5)
            assert scheduler.last_error == "execution_ownership_lost"
        assert len(runtime.requests) == count + 1

    asyncio.run(exercise())


@pytest.mark.parametrize("overlap", ["skip", "queue"])
def test_unknown_effect_never_retried_and_overlap_requires_reconciliation(
    studio, monkeypatch, overlap
):
    client, _, runtime, app = studio
    definition, _, clock = scheduled(
        studio, policy={"max_attempts": 3, "overlap": overlap}
    )
    enable(client, definition)
    original = runtime.execute_direct_turn
    calls = []

    async def uncertain(request, ctx):
        calls.append(request)
        raise ConnectionResetError("Lost response after possible runtime acceptance")

    monkeypatch.setattr(runtime, "execute_direct_turn", uncertain)
    body = {"expected_revision": 1, "idempotency_key": "uncertain"}
    first = post(client, f"/automations/{definition['id']}/run", body)
    assert first["status"] == "outcome_unknown" and first["run_id"]
    assert post(client, f"/automations/{definition['id']}/run", body) == first
    clock[0] = instant(definition["next_run_at"])
    asyncio.run(app.state.automations.tick())
    assert len(calls) == 1
    statuses = {r["status"] for r in occurrences(client, definition)}
    assert statuses == {"outcome_unknown", "skipped" if overlap == "skip" else "queued"}
    post(
        client,
        f"/automations/{definition['id']}/occurrences/{first['id']}/reconcile",
        {
            "acknowledge_no_retry": True,
            "reason": "Operator acknowledges unknown; no retry and Core reservation remains held.",
        },
    )
    monkeypatch.setattr(runtime, "execute_direct_turn", original)
    asyncio.run(app.state.automations.tick())
    assert len(calls) == 1
    with app.state.db.session() as session:
        assert session.get(RunStateModel, first["run_id"]).status == "outcome_unknown"


def test_workflow_schedule_keeps_three_tasks_review_and_automation_lineage(workflow):
    client, db, runtime, app, saved, version = workflow
    studio = (client, db, runtime, app)
    definition, _, _ = scheduled(
        studio, kind="workflow", workflow_target=(saved, version)
    )
    enable(client, definition)
    result = post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "workflow"},
    )
    assert result["status"] == "waiting_review"
    run = client.get(PREFIX + "/workflow-runs/" + result["run_id"]).json()
    assert run["automation_reference"]["occurrence_id"] == result["id"]
    assert (
        sum(
            t["status"] == "completed"
            for t in run["tasks"]
            if t["node_id"] in {"research", "content", "website"}
        )
        == 3
    )
    artifact = client.get(PREFIX + "/outputs/" + run["artifact_id"]).json()
    post(
        client,
        f"/workflow-runs/{run['id']}/review",
        {
            "digest": artifact["digest"],
            "decision": "accepted",
            "reason": "Human accepted actual scheduled staging artifact",
        },
    )
    asyncio.run(app.state.automations.tick())
    assert occurrences(client, definition)[0]["status"] == "completed"


def test_capabilities_are_read_only_default_deny_and_scope_safe(studio):
    client, db, _, app = studio
    data = client.get(PREFIX + "/capabilities").json()
    assert data["entitlement"] == "unknown" and data["provider_hard_cost_cap"] is False
    assert data["local_offline_execution"] is False
    for capability in data["capabilities"]:
        assert capability["grants"] == []
        if capability["risk"] == "privileged":
            assert (
                capability["available"] is False
                and capability["effective_permission"] is False
            )
    assert (
        client.post(PREFIX + "/capabilities", json={"grant": "host.file"}).status_code
        == 405
    )
    definition, _, _ = scheduled(studio)
    assert (
        client.post(
            PREFIX + f"/automations/{definition['id']}/run",
            json={"expected_revision": 1, "idempotency_key": "not-approved"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            PREFIX + "/automations",
            json={"owner_actor_id": "forged", "command": "whoami"},
        ).status_code
        == 422
    )
    assert client.get(PREFIX + "/automations?limit=101").status_code == 422
    assert client.get(PREFIX + "/automations?q=x&q=y").status_code == 422
    assert client.get(
        PREFIX.replace(DEV_PROJECT, "other-project")
        + f"/automations/{definition['id']}"
    ).status_code in {403, 404}
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(
            user_id=DEV_ACTOR
        ).one().role = "viewer"
        from database.repositories.organization_repo import OrganizationRepository

        OrganizationRepository(session).add_project_member(
            DEV_PROJECT, DEV_ACTOR, "viewer"
        )
    registry = client.get(PREFIX + "/capabilities").json()
    assert not next(
        c
        for c in registry["capabilities"]
        if c["namespace"] == "aryn.automation.schedule"
    )["effective_permission"]
    assert (
        client.post(
            PREFIX + "/automations", json=definition["configuration"]
        ).status_code
        == 403
    )
    assert client.get(PREFIX + "/automations").status_code == 200


@pytest.mark.parametrize(
    "attack", ["payload", "approval", "activation", "target_hash", "tool", "identity"]
)
def test_stale_or_forged_authority_never_dispatches(studio, attack):
    client, db, runtime, _ = studio
    definition, body, _ = scheduled(studio)
    enable(client, definition)
    count = len(runtime.requests)
    if attack in {"target_hash", "tool", "identity"}:
        if attack == "target_hash":
            body["target"]["payload_hash"] = "a" * 64
        else:
            body[attack] = {"command": "whoami"} if attack == "tool" else "admin"
        assert client.post(PREFIX + "/automations", json=body).status_code in {409, 422}
    else:
        with db.engine.begin() as connection:
            if attack == "payload":
                connection.execute(
                    text(
                        "UPDATE automation_definitions SET details_json='{}' WHERE id=:id"
                    ),
                    {"id": definition["id"]},
                )
            elif attack == "approval":
                connection.execute(
                    text(
                        "UPDATE approvals SET attestation='invalid' WHERE target_id=:id"
                    ),
                    {"id": definition["id"]},
                )
            else:
                connection.execute(
                    text(
                        "UPDATE agent_assignments SET current_transition_id='changed' WHERE id=:id"
                    ),
                    {"id": body["target"]["id"]},
                )
        response = client.post(
            PREFIX + f"/automations/{definition['id']}/run",
            json={"expected_revision": 1, "idempotency_key": "rejected"},
        )
        assert response.status_code in {200, 403, 409}, response.text
        if response.status_code == 200:
            assert (
                response.json()["status"] == "blocked"
                and response.json()["run_id"] is None
            )
    assert len(runtime.requests) == count


@pytest.mark.parametrize("checkpoint", ["before_claim", "after_claim"])
def test_restart_interrupted_occurrence_is_unknown_and_fenced(
    studio, monkeypatch, checkpoint
):
    from database.connection import DatabaseManager, create_db_engine
    from services.api.studio import create_app
    from modules.core.workflows.ownership import ExecutionOwnershipError
    from packages.contracts.automation import AutomationStateInput

    client, db, runtime, app = studio
    definition, _, _ = scheduled(studio)
    enable(client, definition)
    old = app.state.automations
    count = len(runtime.requests)

    class ProcessCrash(BaseException):
        pass

    if checkpoint == "before_claim":

        async def crash():
            raise ProcessCrash()

        monkeypatch.setattr(old, "require_runtime", crash)
    else:

        async def crash(*args, **kwargs):
            raise ProcessCrash()

        # Bypass the direct-turn handler after its durable Core claim was committed.
        monkeypatch.setattr(app.state.coordinator, "execute_managed_direct_turn", crash)
    with pytest.raises(ProcessCrash):
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
        asyncio.run(
            old.manual(
                ctx,
                definition["id"],
                ManualOccurrence(expected_revision=1, idempotency_key="interrupted"),
            )
        )
    with db.session() as session:
        row = session.query(AutomationOccurrenceModel).one()
        assert row.status == "dispatching"
        identifier = row.id
    url = str(db.engine.url)
    db.engine.dispose()
    new = DatabaseManager(create_db_engine(url))
    try:
        restarted = create_app(new, runtime, testing=True)
        ctx = restarted.state.binder.create_trusted_context(
            DEV_ACTOR, DEV_ORG, DEV_PROJECT
        )
        with new.session() as session:
            _, occurrence = restarted.state.automations.get(
                session, AutomationOccurrenceModel, ctx, identifier
            )
            assert occurrence["status"] == "outcome_unknown"
        asyncio.run(restarted.state.automations.tick())
        with pytest.raises(ExecutionOwnershipError):
            old.state(
                ctx,
                definition["id"],
                AutomationStateInput(expected_revision=1, enabled=False),
            )
        assert len(runtime.requests) == count
    finally:
        new.engine.dispose()


def test_sqlite_nonerasable_history_and_populated_rollback(studio):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import DBAPIError

    client, db, _, _ = studio
    definition, _, _ = scheduled(studio)
    enable(client, definition)
    post(
        client,
        f"/automations/{definition['id']}/run",
        {"expected_revision": 1, "idempotency_key": "persistent-history"},
    )
    for statement in (
        "DELETE FROM automation_definitions",
        "DELETE FROM automation_occurrences",
        "DELETE FROM automation_events",
        "UPDATE automation_events SET details_json='{}'",
        "INSERT OR REPLACE INTO automation_events SELECT * FROM automation_events",
    ):
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(statement))
    config = Config("alembic.ini")
    with db.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.stamp(config, "020_core_automations")
    with (
        pytest.raises(RuntimeError, match="Populated Core"),
        db.engine.begin() as connection,
    ):
        config.attributes["connection"] = connection
        command.downgrade(config, "019_intelligence_recovery")
    assert client.get(PREFIX + f"/automations/{definition['id']}").status_code == 200
