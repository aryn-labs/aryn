"""Unified Runs/Cron integrate actual API, governance, signatures and disposable Core."""

import asyncio
import copy
import uuid
from tests.integration.test_studio_api import studio as studio, PREFIX, DEV_PROJECT
from tests.integration.test_core_automations import scheduled, enable, occurrences
from tests.integration.test_workflow_execution import workflow as workflow, start
from modules.core.automations.recurrence import instant
from database.schema import RunStateModel


def test_automation_agent_projection_lineage_private_modes_search_cursor_and_stop(
    studio,
):
    client, db, _, _ = studio
    definition, _, _ = scheduled(studio)
    enable(client, definition)
    receipt = client.post(
        PREFIX + f"/automations/{definition['id']}/run",
        json={"expected_revision": 1, "idempotency_key": "runs-inspection"},
    ).json()
    identifier = receipt["run_id"]
    detail = client.get(PREFIX + "/executions/agent/" + identifier)
    assert detail.status_code == 200, detail.text
    value = detail.json()
    assert value["verified"] and value["source"] == "automation"
    assert value["references"]["automation_id"] == definition["id"]
    assert value["references"]["occurrence_id"] == receipt["id"]
    assert (
        value["io"]["output"]
        and value["timeline"]
        and value["usage"]["availability"] == "measured"
    )
    assert not any(
        "attestation" in key or "owner_id" in key for key in value["references"]
    )
    inventory = client.get(PREFIX + "/executions?q=" + identifier).json()
    assert [row["id"] for row in inventory["items"]] == [identifier]
    first = client.get(PREFIX + "/executions?limit=1").json()
    if first["next_cursor"]:
        assert (
            client.get(
                PREFIX + "/executions",
                params={"limit": 1, "after": first["next_cursor"]},
            ).status_code
            == 200
        )
        assert (
            client.get(
                PREFIX + "/executions",
                params={"limit": 1, "after": first["next_cursor"], "order": "asc"},
            ).status_code
            == 422
        )
    for suffix in (
        "?q=a&q=b",
        "?limit=101",
        "?order=unsafe",
        "?since=2026-01-01",
        "?kind=bench",
        "?unknown=x",
    ):
        assert client.get(PREFIX + "/executions" + suffix).status_code == 422
    assert client.get(
        PREFIX.replace(DEV_PROJECT, "foreign") + "/executions/agent/" + identifier
    ).status_code in (403, 404)
    assert (
        client.post(
            PREFIX + "/executions/agent/" + identifier + "/stop",
            json={},
            headers={"X-CSRF-Token": "invalid"},
        ).status_code
        == 403
    )
    with db.session() as session:
        bench = session.query(RunStateModel).filter_by(execution_mode="bench").first()
        if bench:
            assert (
                client.get(PREFIX + "/executions/agent/" + bench.id).status_code == 404
            )


def test_workflow_parent_projection_excludes_internal_core_tasks(workflow):
    client, _, _, _, _, version = workflow
    run = start(workflow, "execution-center")
    detail = client.get(PREFIX + "/executions/workflow/" + run["id"])
    assert detail.status_code == 200, detail.text
    value = detail.json()
    assert value["workflow_version"]["id"] == version["id"]
    assert value["workflow_run"]["traversed_edges"] == run["traversed_edges"]
    assert not {"owner_id", "request_hash", "actor_id"}.intersection(
        value["workflow_run"]
    )
    listed = client.get(PREFIX + "/executions?kind=workflow").json()["items"]
    assert run["id"] in [item["id"] for item in listed]
    agents = client.get(PREFIX + "/executions?kind=agent").json()["items"]
    task_ids = {task["core_run_id"] for task in run["tasks"] if task["core_run_id"]}
    assert not task_ids.intersection(item["id"] for item in agents)
    for identifier in task_ids:
        assert client.get(PREFIX + "/executions/agent/" + identifier).status_code == 404


def test_cron_real_occurrence_daily_budget_approval_edit_and_cold_catalog(studio):
    client, _, runtime, app = studio
    definition, body, clock = scheduled(studio, policy={"max_runs_per_day": 1})
    old_hash = definition["payload_hash"]
    body = copy.deepcopy(body)
    body["schedule"].update(kind="cron", cron_expression="* * * * *")
    body["expected_revision"] = definition["revision"]
    changed = client.post(PREFIX + "/automations/" + definition["id"], json=body)
    assert changed.status_code == 200, changed.text
    definition = changed.json()
    assert definition["status"] == "paused" and definition["payload_hash"] != old_hash
    assert not client.get(PREFIX + "/automations/" + definition["id"]).json()[
        "approval_verified"
    ]
    enable(client, definition)
    app.state.coordinator.model_router.replace_catalog([])
    before = len(runtime.requests)
    clock[0] = instant(definition["next_run_at"])
    asyncio.run(app.state.automations.tick())
    assert occurrences(client, definition)[0]["status"] == "completed"
    clock[0] = instant(
        client.get(PREFIX + "/automations/" + definition["id"]).json()["next_run_at"]
    )
    asyncio.run(app.state.automations.tick())
    assert occurrences(client, definition)[0]["status"] == "blocked"
    assert len(runtime.requests) == before + 1
    assert (
        len(
            client.post(
                PREFIX + "/automation-preview", json={"schedule": body["schedule"]}
            ).json()["instants"]
        )
        == 5
    )


def test_manual_async_occurrence_is_durable_without_browser_or_second_runner(studio):
    client, _, runtime, app = studio
    definition, _, _ = scheduled(studio)
    enable(client, definition)
    body = {"expected_revision": 1, "idempotency_key": uuid.uuid4().hex}
    before = len(runtime.requests)
    receipt = client.post(
        PREFIX + f"/automations/{definition['id']}/run",
        json=body,
        headers={"Prefer": "respond-async"},
    )
    assert receipt.status_code == 200 and receipt.json()["status"] == "queued"
    assert len(runtime.requests) == before
    asyncio.run(app.state.automations.tick())
    repeated = client.post(
        PREFIX + f"/automations/{definition['id']}/run",
        json=body,
        headers={"Prefer": "respond-async"},
    ).json()
    assert repeated["id"] == receipt.json()["id"] and repeated["status"] == "completed"
    assert len(runtime.requests) == before + 1


def test_local_webhook_unavailable_and_no_fake_url_or_credential(studio):
    client, _, runtime, _ = studio
    capability = client.get(PREFIX + "/automation-triggers").json()
    assert not capability["webhook_available"] and not capability["mcp_available"]
    definition, body, _ = scheduled(studio)
    body["schedule"]["kind"] = "webhook"
    assert client.post(PREFIX + "/automations", json=body).status_code == 503
    assert (
        client.post(
            PREFIX + f"/automations/{definition['id']}/webhook",
            json={"expected_revision": 1, "action": "rotate"},
        ).status_code
        == 503
    )
    before = len(runtime.requests)
    assert (
        client.post(
            "/ingress/webhooks/opaque", json={"event_id": "a", "event": "trigger"}
        ).status_code
        == 503
    )
    assert len(runtime.requests) == before


def test_private_chat_is_excluded_even_with_project_admin_and_known_core_id(studio):
    from tests.integration.test_conversations import payload, complete
    from database.schema import ConversationTurnModel

    client, db, _, _ = studio
    policy = client.get(PREFIX + "/chat/provider-consent").json()["models"][
        "test/model-a"
    ]
    assert (
        client.post(
            PREFIX + "/chat/provider-consent",
            json={"model": "test/model-a", "policy": policy["policy"]},
        ).status_code
        == 200
    )
    response = client.post(PREFIX + "/chat/conversations", json=payload())
    assert response.status_code == 202
    complete(client, response.json()["id"])
    with db.session() as session:
        identifier = session.query(ConversationTurnModel).first().run_id
    assert client.get(PREFIX + "/executions/agent/" + identifier).status_code == 404
    assert client.get(PREFIX + "/executions?q=" + identifier).json()["items"] == []


def test_cursor_filter_order_tamper_and_target_checks_are_bound_to_actual_scope(studio):
    client, _, _, _ = studio
    definition, body, _ = scheduled(studio)
    enable(client, definition)
    ids = {
        client.post(
            PREFIX + f"/automations/{definition['id']}/run",
            json={"expected_revision": 1, "idempotency_key": "cursor-" + str(i)},
        ).json()["run_id"]
        for i in range(3)
    }
    page = client.get(PREFIX + "/executions?limit=1&order=asc").json()
    found = [page["items"][0]["id"]]
    assert page["next_cursor"]
    original = page["next_cursor"]
    while page["next_cursor"]:
        page = client.get(
            PREFIX + "/executions",
            params={"limit": 1, "order": "asc", "after": page["next_cursor"]},
        ).json()
        found.extend(item["id"] for item in page["items"])
    assert len(found) == 3 and set(found) == ids
    for query in (
        {"after": original, "order": "desc"},
        {"after": original, "order": "asc", "kind": "agent"},
        {"after": "tampered"},
    ):
        assert client.get(PREFIX + "/executions", params=query).status_code == 422
    assert client.get(PREFIX + "/executions", params={"q": "%_"}).json()["items"] == []
    assert (
        client.get(PREFIX + "/executions", params={"status": "failed"}).json()["items"]
        == []
    )
    assert (
        client.get(
            PREFIX + "/executions",
            params={"since": "2030-01-01T00:00:00Z", "until": "2020-01-01T00:00:00Z"},
        ).status_code
        == 422
    )
    assert client.get(PREFIX + "/automations?trigger=cron").json()["items"] == []
    assert [
        item["id"]
        for item in client.get(PREFIX + "/automations?trigger=interval").json()["items"]
    ] == [definition["id"]]
    assert client.get(PREFIX + "/automations?trigger=forged").status_code == 422
    assert client.post(
        PREFIX + "/automation-targets/check", json=body["target"]
    ).json()["available"]
    assert client.post(
        PREFIX.replace(DEV_PROJECT, "foreign") + "/automation-targets/check",
        json=body["target"],
    ).status_code in (403, 404)
    assert (
        client.post(
            PREFIX + "/automation-targets/check",
            json={**body["target"], "payload_hash": "0" * 64},
        ).status_code
        == 409
    )


def test_preview_claim_visible_only_to_its_actor_and_signed_accepted_evidence(studio):
    from tests.integration.test_agent_canvas import setup, preview_body, wait
    from services.api.studio import DEV_ACTOR, DEV_ORG
    from database.repositories.organization_repo import OrganizationRepository

    client, db, _, app = studio
    root, _, _ = setup(client)
    identifier = client.post(root + "/preview-runs", json=preview_body()).json()[
        "result"
    ]["run_id"]
    wait(client, root + "/preview-runs/" + identifier)
    assert (
        client.get(PREFIX + "/executions/agent/" + identifier).json()["source"]
        == "agent_preview"
    )
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.add_member(DEV_ORG, "other-observer", "admin")
        repo.add_project_member(DEV_PROJECT, "other-observer", "operator")
    other = app.state.binder.create_trusted_context(
        "other-observer", DEV_ORG, DEV_PROJECT
    )
    assert app.state.executions.catalog(other)["items"] == []
    from database.repositories.exceptions import EntityNotFoundError
    import pytest

    with pytest.raises(EntityNotFoundError):
        app.state.executions.detail(other, "agent", identifier)
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    assert app.state.executions.catalog(ctx)["items"][0]["id"] == identifier
