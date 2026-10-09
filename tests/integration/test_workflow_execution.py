"""Actual three-task Core path and adversarial graph/storage/reviewer boundaries."""

import copy
import json

import pytest
from sqlalchemy import text

from tests.integration.test_studio_api import (
    studio as studio,
    draft,
    promoted,
    PREFIX,
    ORIGIN,
)
from services.api.studio import create_app, DEV_ORG, DEV_ACTOR
from fastapi.testclient import TestClient
from database.repositories.organization_repo import OrganizationRepository
from sqlalchemy.exc import IntegrityError


def graph(assignment, version):
    nodes = [
        {"id": "input", "label": "Input", "kind": "start"},
        {
            "id": "research",
            "label": "Research",
            "kind": "agent",
            "input_schema": "text",
            "output_schema": "brief",
            "assignment_id": assignment["id"],
            "agent_version_id": version["id"],
        },
        {
            "id": "handoff",
            "label": "Brief handoff",
            "kind": "handoff",
            "input_schema": "brief",
            "output_schema": "brief",
        },
        {
            "id": "content",
            "label": "Content",
            "kind": "agent",
            "input_schema": "brief",
            "output_schema": "content",
            "assignment_id": assignment["id"],
            "agent_version_id": version["id"],
        },
        {
            "id": "website",
            "label": "Website",
            "kind": "agent",
            "input_schema": "content",
            "output_schema": "website",
            "renderer": "static-document-v1",
        },
        {
            "id": "review",
            "label": "Human review",
            "kind": "review",
            "input_schema": "website",
            "output_schema": "website",
        },
        {
            "id": "end",
            "label": "Output",
            "kind": "end",
            "input_schema": "website",
            "output_schema": "website",
        },
    ]
    return {
        "nodes": nodes,
        "edges": [
            {"id": f"edge_{i}", "source": a["id"], "target": b["id"]}
            for i, (a, b) in enumerate(zip(nodes, nodes[1:], strict=False))
        ],
    }


@pytest.fixture
def workflow(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    # Distinct governed Content version/assignment, no synthetic publication.
    content_bp, content_version = draft(client, "content-task")
    client.post(
        PREFIX + f"/versions/{content_version['id']}/bench",
        json={"allow_remote_model": True},
    ).raise_for_status()
    client.post(
        PREFIX + f"/versions/{content_version['id']}/approve",
        json={"payload_hash": content_version["payload_hash"], "comments": "Reviewed"},
    ).raise_for_status()
    client.post(
        PREFIX + f"/versions/{content_version['id']}/publish", json={}
    ).raise_for_status()
    content_assignment = client.post(
        PREFIX + "/assignments",
        json={
            "blueprint_id": content_bp["id"],
            "version_id": content_version["id"],
            "role_name": "Content writer",
        },
    ).json()
    definition = {
        "name": "Research content document",
        "expected_revision": 0,
        "graph": graph(assignment, version),
        "positions": [{"id": "input", "x": 30, "y": 100}],
    }
    definition["graph"]["nodes"][3].update(
        assignment_id=content_assignment["id"], agent_version_id=content_version["id"]
    )
    saved = client.post(PREFIX + "/workflows", json=definition)
    assert saved.status_code == 201, saved.text
    frozen = client.post(
        PREFIX + f"/workflows/{saved.json()['id']}/versions",
        json={"expected_revision": 1},
    )
    assert frozen.status_code == 201, frozen.text
    return client, db, runtime, app, saved.json(), frozen.json()


def start(workflow, key="three-task"):
    client, _, _, _, saved, version = workflow
    response = client.post(
        PREFIX + f"/workflows/{saved['id']}/runs",
        json={
            "version_id": version["id"],
            "input": "Research a safe static document",
            "idempotency_key": key,
            "allow_remote_model": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_three_tasks_exact_handoff_review_restart_download(workflow, decision):
    client, db, runtime, _, saved, version = workflow
    count = len(runtime.requests)
    run = start(workflow)
    assert run["status"] == "waiting_review", run
    assert (
        len(runtime.requests) == count + 2
    )  # Third task is the actual allowlisted renderer.
    tasks = {t["node_id"]: t for t in run["tasks"]}
    assert all(
        tasks[id]["status"] == "completed" for id in ("research", "content", "website")
    )
    assert (
        tasks["content"]["input_artifact_id"] == tasks["research"]["output_artifact_id"]
    )
    assert (
        tasks["website"]["input_artifact_id"] == tasks["content"]["output_artifact_id"]
    )
    brief = client.get(
        PREFIX + f"/outputs/{tasks['research']['output_artifact_id']}/download"
    )
    assert brief.status_code == 200, brief.text
    assert runtime.requests[-1].prompt == json.loads(brief.content)["text"]
    artifact = client.get(PREFIX + f"/outputs/{run['artifact_id']}").json()
    assert artifact["validation"] == "inert-static-document" and artifact[
        "consumers"
    ] == ["review"]
    content = client.get(
        PREFIX + f"/outputs/{tasks['content']['output_artifact_id']}"
    ).json()
    assert (
        content["agent_version_id"] == version["graph"]["nodes"][3]["agent_version_id"]
    )
    assert (
        content["core_run_id"] == tasks["content"]["core_run_id"]
        and content["model"] == "test/model-a"
    )
    assert start(workflow) == run and len(runtime.requests) == count + 2
    assert (
        client.get(PREFIX + f"/workflows/{saved['id']}").json()["positions"]
        == saved["positions"]
    )
    restarted = create_app(db, runtime, testing=True)
    with TestClient(restarted, base_url=ORIGIN, client=("127.0.0.1", 1)) as other:
        csrf = other.post("/api/session", json={}, headers={"Origin": ORIGIN}).json()[
            "csrf"
        ]
        other.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
        assert (
            other.get(PREFIX + f"/workflow-runs/{run['id']}").json()["status"]
            == "waiting_review"
        )
        body = {
            "digest": artifact["digest"],
            "decision": decision,
            "reason": "Exact artifact inspected",
        }
        receipt = other.post(PREFIX + f"/workflow-runs/{run['id']}/review", json=body)
        assert receipt.status_code == 200, receipt.text
        assert (
            other.post(PREFIX + f"/workflow-runs/{run['id']}/review", json=body).json()
            == receipt.json()
        )
        assert other.get(PREFIX + f"/workflow-runs/{run['id']}").json()["status"] == (
            "completed" if decision == "accepted" else "rejected"
        )
        download = other.get(PREFIX + f"/outputs/{artifact['id']}/download")
        assert (
            download.status_code == 200
            and "attachment" in download.headers["content-disposition"]
        )
        assert (
            "sandbox" in download.headers["content-security-policy"]
            and download.headers["x-content-type-options"] == "nosniff"
        )
        assert (
            other.get(PREFIX + "/deliverables").json()["items"][0]["digest"]
            == artifact["digest"]
        )
    with db.session() as s:
        assert (
            s.execute(text("SELECT COUNT(*) FROM workflow_deliverables")).scalar() == 1
        )
        assert (
            s.execute(
                text("SELECT COUNT(*) FROM audit_events WHERE event_type=:event"),
                {"event": "workflow.review." + decision},
            ).scalar()
            == 1
        )
    assert not runtime.tools


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate",
        "port",
        "schema",
        "cycle",
        "orphan",
        "fanout",
        "pin",
        "missing",
        "review_bypass",
        "task_count",
    ],
)
def test_invalid_graph_authoritative(workflow, attack):
    client, _, runtime, _, saved, _ = workflow
    body = {k: copy.deepcopy(saved[k]) for k in ("name", "graph", "positions")}
    body["expected_revision"] = 1
    nodes, edges = body["graph"]["nodes"], body["graph"]["edges"]
    if attack == "duplicate":
        nodes[1]["id"] = nodes[0]["id"]
    if attack == "port":
        edges[0]["source_port"] = "yes"
    if attack == "schema":
        nodes[1]["input_schema"] = "brief"
    if attack == "cycle":
        edges[1]["target"] = "research"
    if attack == "orphan":
        nodes.append({"id": "orphan", "label": "Orphan", "kind": "handoff"})
    if attack == "fanout":
        edges.append({"id": "extra", "source": "input", "target": "research"})
    if attack == "pin":
        nodes[1]["agent_version_id"] = nodes[3]["agent_version_id"]
    if attack == "missing":
        nodes[1]["assignment_id"] = "missing"
    if attack == "review_bypass":
        edges[4]["target"] = "end"
    if attack == "task_count":
        for node in nodes:
            if node["kind"] == "agent":
                node.update(
                    kind="handoff",
                    assignment_id=None,
                    agent_version_id=None,
                    renderer=None,
                    output_schema=node["input_schema"],
                )
    assert (
        client.post(PREFIX + f"/workflows/{saved['id']}", json=body).status_code == 200
    )
    before = len(runtime.requests)
    rejected = client.post(PREFIX + f"/workflows/{saved['id']}/validate", json={})
    assert rejected.status_code == 422 and rejected.json()["issues"]
    assert (
        client.post(
            PREFIX + f"/workflows/{saved['id']}/versions", json={"expected_revision": 2}
        ).status_code
        == 422
    )
    assert len(runtime.requests) == before


def test_stale_cas_hash_approval_review_role_and_tenant(workflow):
    client, db, _, _, saved, version = workflow
    body = {k: saved[k] for k in ("name", "graph", "positions")}
    assert (
        client.post(
            PREFIX + f"/workflows/{saved['id']}", json={**body, "expected_revision": 0}
        ).status_code
        == 409
    )
    run = start(workflow)
    artifact = client.get(PREFIX + f"/outputs/{run['artifact_id']}").json()
    review = {"digest": "a" * 64, "decision": "accepted", "reason": "Stale"}
    assert (
        client.post(
            PREFIX + f"/workflow-runs/{run['id']}/review", json=review
        ).status_code
        == 409
    )
    with db.session(write=True) as s:
        OrganizationRepository(s).get_member(DEV_ORG, DEV_ACTOR).role = "viewer"
    review["digest"] = artifact["digest"]
    assert (
        client.post(
            PREFIX + f"/workflow-runs/{run['id']}/review", json=review
        ).status_code
        == 403
    )
    assert (
        client.post(
            PREFIX + f"/workflows/{saved['id']}/runs",
            json={
                "version_id": version["id"],
                "input": "Other",
                "idempotency_key": "other",
                "allow_remote_model": True,
            },
        ).status_code
        == 403
    )
    for path in (
        f"/outputs/{artifact['id']}",
        f"/outputs/{artifact['id']}/download",
        f"/workflow-runs/{run['id']}",
        f"/workflow-versions/{version['id']}",
    ):
        assert client.get("/api/projects/unauthorized" + path).status_code == 403
    with db.session(write=True) as s:
        OrganizationRepository(s).get_member(DEV_ORG, DEV_ACTOR).role = "admin"
    assert start(workflow, "three-task")["id"] == run["id"]
    assert (
        client.post(
            PREFIX + f"/workflows/{saved['id']}/runs",
            json={
                "version_id": version["id"],
                "input": "Other",
                "idempotency_key": "three-task",
                "allow_remote_model": True,
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "attack", ["script", "oversize", "unknown", "timeout", "budget", "sandbox"]
)
def test_execution_failure_and_static_isolation(workflow, monkeypatch, attack):
    client, db, runtime, _, _, _ = workflow
    original = runtime.execute_direct_turn

    async def execute(request, ctx):
        if attack == "timeout":
            raise TimeoutError("synthetic")
        result = await original(request, ctx)
        if attack == "script":
            result.output = '<script>fetch("https://evil.invalid")</script><img src=x onerror=alert(1)>'
        if attack == "oversize":
            result.output = "x" * 70000
        if attack == "unknown":
            result.usage.availability = "unavailable"
        return result

    runtime.execute_direct_turn = execute
    if attack == "budget":
        with db.session(write=True) as s:
            s.execute(text("UPDATE usage_budgets SET max_tokens_per_run=1"))
    if attack == "sandbox":
        import modules.core.workflows.executor as engine

        real_renderer = engine.render_document
        calls = 0

        def broken(text):
            nonlocal calls
            calls += 1
            return b"<script>bad()</script>" if calls == 1 else real_renderer(text)

        monkeypatch.setattr(engine, "render_document", broken)
    run = start(workflow)
    if attack == "script":
        assert run["status"] == "waiting_review"
        preview = client.get(PREFIX + f"/outputs/{run['artifact_id']}/preview")
        assert "<script>" not in preview.text and "&lt;script&gt;" in preview.text
        assert "default-src 'none'" in preview.headers["content-security-policy"]
    else:
        assert run["status"] in {"failed", "outcome_unknown"}, run
        count = len(runtime.requests)
        assert start(workflow) == run and len(runtime.requests) == count
    assert runtime.tools == []


@pytest.mark.parametrize("table", ["workflow_versions", "workflow_artifacts"])
def test_immutable_raw_sql_and_corruption_fail_closed(workflow, table):
    client, db, _, _, _, version = workflow
    run = start(workflow)
    id = version["id"] if table == "workflow_versions" else run["artifact_id"]
    with pytest.raises(IntegrityError), db.engine.begin() as c:
        c.execute(
            text(f"UPDATE {table} SET attestation='invalid' WHERE id=:id"), {"id": id}
        )
    # Simulate compromised migration owner; independent signature/head and blob
    # digest still reject data even with SQL trigger intentionally removed here.
    with db.engine.begin() as c:
        c.execute(text(f"DROP TRIGGER aryn_{table}_update"))
        if table == "workflow_artifacts":
            c.execute(
                text("UPDATE workflow_artifacts SET blob=:blob WHERE id=:id"),
                {"blob": b"corrupted", "id": id},
            )
        else:
            c.execute(
                text(
                    "UPDATE workflow_versions SET details_json=replace(details_json,'static-document-v1','unsafe-renderer') WHERE id=:id"
                ),
                {"id": id},
            )
    endpoint = (
        f"/workflow-versions/{id}"
        if table == "workflow_versions"
        else f"/outputs/{id}/download"
    )
    assert client.get(PREFIX + endpoint).status_code != 200


def test_version_revision_relationship_fail_closed(workflow):
    client, db, runtime, _, saved, version = workflow
    assert version["revision"] == saved["revision"] == 1
    with db.engine.begin() as connection:
        connection.execute(text("DROP TRIGGER aryn_workflow_versions_update"))
        connection.execute(
            text("UPDATE workflow_versions SET revision=2 WHERE id=:id"),
            {"id": version["id"]},
        )
    assert client.get(PREFIX + f"/workflow-versions/{version['id']}").status_code != 200
    count = len(runtime.requests)
    assert (
        client.post(
            PREFIX + f"/workflows/{saved['id']}/runs",
            json={
                "version_id": version["id"],
                "input": "Integrity check",
                "idempotency_key": "tampered-revision",
                "allow_remote_model": True,
            },
        ).status_code
        != 200
    )
    assert len(runtime.requests) == count


def test_condition_expression_and_path_attack(workflow):
    client, _, _, _, saved, _ = workflow
    body = {k: copy.deepcopy(saved[k]) for k in ("name", "graph", "positions")}
    body["expected_revision"] = 1
    body["graph"]["nodes"][2].update(
        kind="condition", predicate={"operator": "eval", "literal": "__import__('os')"}
    )
    assert (
        client.post(PREFIX + f"/workflows/{saved['id']}", json=body).status_code == 422
    )
    body["graph"]["nodes"][4]["renderer"] = "../../server-key"
    assert (
        client.post(PREFIX + f"/workflows/{saved['id']}", json=body).status_code == 422
    )
    assert (
        client.get(PREFIX + "/outputs/..%2F..%2Fserver-key/download").status_code != 200
    )
    assert client.get(PREFIX + "/outputs?limit=1000").status_code == 422
    assert client.get(PREFIX + "/workflows?limit=1&limit=2").status_code == 422


def test_cancel_waiting_without_approval_and_fenced_owner(workflow):
    client, _, runtime, app, _, _ = workflow
    run = start(workflow)
    assert (
        client.post(PREFIX + f"/workflow-runs/{run['id']}/stop", json={}).json()[
            "status"
        ]
        == "cancelled"
    )
    count = len(runtime.requests)
    assert start(workflow)["status"] == "cancelled" and len(runtime.requests) == count
    app.state.coordinator.authority.valid = False
    try:
        assert (
            client.post(
                PREFIX + f"/workflow-runs/{run['id']}/stop", json={}
            ).status_code
            != 200
        )
    finally:
        app.state.coordinator.authority.valid = True


@pytest.mark.parametrize("branch", [True, False])
def test_typed_condition_selects_one_bounded_path(workflow, branch):
    client, _, runtime, _, saved, _ = workflow
    body = {k: copy.deepcopy(saved[k]) for k in ("name", "graph", "positions")}
    body["expected_revision"] = 1
    handoff = body["graph"]["nodes"][2]
    handoff.update(
        kind="condition",
        predicate={
            "operator": "nonempty" if branch else "equals",
            "literal": "never-match-fixture",
        },
    )
    for name in ("yes_path", "no_path"):
        body["graph"]["nodes"].append(
            {
                "id": name,
                "label": name,
                "kind": "handoff",
                "input_schema": "brief",
                "output_schema": "brief",
            }
        )
    edges = body["graph"]["edges"]
    body["graph"]["edges"] = [e for e in edges if e["source"] != "handoff"] + [
        {
            "id": "yes_edge",
            "source": "handoff",
            "source_port": "yes",
            "target": "yes_path",
        },
        {
            "id": "no_edge",
            "source": "handoff",
            "source_port": "no",
            "target": "no_path",
        },
        {"id": "yes_join", "source": "yes_path", "target": "content"},
        {"id": "no_join", "source": "no_path", "target": "content"},
    ]
    assert (
        client.post(PREFIX + f"/workflows/{saved['id']}", json=body).status_code == 200
    )
    frozen = client.post(
        PREFIX + f"/workflows/{saved['id']}/versions", json={"expected_revision": 2}
    )
    assert frozen.status_code == 201, frozen.text
    changed = (*workflow[:-1], frozen.json())
    count = len(runtime.requests)
    run = start(changed)
    tasks = {t["node_id"]: t for t in run["tasks"]}
    assert run["status"] == "waiting_review" and len(runtime.requests) == count + 2
    assert tasks["yes_path" if branch else "no_path"]["status"] == "completed"
    assert tasks["no_path" if branch else "yes_path"]["status"] == "skipped"


def test_restart_unknown_claim_no_retry_and_waiting_artifact_survives(workflow):
    import asyncio
    from database.connection import DatabaseManager, create_db_engine
    from packages.contracts.workflow import StartWorkflow

    client, db, runtime, app, saved, version = workflow
    original = runtime.execute_direct_turn
    surviving = start(workflow, "surviving-review")
    surviving_artifact = client.get(
        PREFIX + f"/outputs/{surviving['artifact_id']}"
    ).json()

    class ProcessLoss(BaseException):
        """Emulate process termination that cannot execute workflow cleanup."""

    async def interrupted(request, ctx):
        raise ProcessLoss("simulated process loss after durable claim")

    runtime.execute_direct_turn = interrupted
    body = StartWorkflow(
        version_id=version["id"],
        input="Interrupted durable workflow",
        idempotency_key="crash",
        allow_remote_model=True,
    )
    ctx = app.state.binder.create_trusted_context(
        DEV_ACTOR, DEV_ORG, PREFIX.split("/")[-1]
    )
    with pytest.raises(ProcessLoss):
        asyncio.run(app.state.workflows.start(ctx, saved["id"], body))
    with db.session() as s:
        id = s.execute(
            text("SELECT id FROM workflow_runs WHERE idempotency_key='crash'")
        ).scalar()
        payload = json.loads(
            s.execute(
                text("SELECT details_json FROM workflow_runs WHERE id=:id"), {"id": id}
            ).scalar()
        )
        assert payload["status"] == "running" and payload["tasks"][1]["core_run_id"]
        assert (
            s.execute(
                text("SELECT COUNT(*) FROM run_states WHERE status='outcome_unknown'")
            ).scalar()
            == 1
        )
    runtime.execute_direct_turn = original
    database_url = db.engine.url
    db.engine.dispose()
    reopened = DatabaseManager(
        create_db_engine(database_url.render_as_string(hide_password=False))
    )
    try:
        new_app = create_app(reopened, runtime, testing=True)
        with TestClient(new_app, base_url=ORIGIN, client=("127.0.0.1", 1)) as other:
            csrf = other.post(
                "/api/session", json={}, headers={"Origin": ORIGIN}
            ).json()["csrf"]
            other.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
            recovered = other.get(PREFIX + f"/workflow-runs/{id}")
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["status"] == "outcome_unknown"
            assert (
                other.get(
                    PREFIX + f"/outputs/{surviving_artifact['id']}/download"
                ).status_code
                == 200
            )
            assert (
                other.post(
                    PREFIX + f"/workflow-runs/{surviving['id']}/review",
                    json={
                        "digest": surviving_artifact["digest"],
                        "decision": "accepted",
                        "reason": "Durable review after owner restart",
                    },
                ).status_code
                == 200
            )
            count = len(runtime.requests)
            retry = other.post(
                PREFIX + f"/workflows/{saved['id']}/runs",
                json=body.model_dump(mode="json"),
            )
            assert (
                retry.json()["status"] == "outcome_unknown"
                and len(runtime.requests) == count
            )
            with reopened.session() as s:
                assert (
                    s.execute(
                        text(
                            "SELECT COUNT(*) FROM run_states WHERE reserved_tokens>0 AND usage_settled=0"
                        )
                    ).scalar()
                    >= 1
                )
            # No authority replacement on the stale engine/coordinator.
            from modules.core.workflows.ownership import ExecutionOwnershipError

            with pytest.raises(ExecutionOwnershipError):
                app.state.coordinator._fence()
    finally:
        reopened.engine.dispose()


def test_concurrent_start_and_review_exactly_once(workflow):
    from concurrent.futures import ThreadPoolExecutor

    client, _, runtime, _, saved, version = workflow
    count = len(runtime.requests)
    body = {
        "version_id": version["id"],
        "input": "Concurrent admission",
        "idempotency_key": "concurrent",
        "allow_remote_model": True,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            f.result(timeout=30)
            for f in [
                pool.submit(
                    client.post, PREFIX + f"/workflows/{saved['id']}/runs", json=body
                )
                for _ in range(2)
            ]
        ]
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert (
        len({r.json()["id"] for r in results}) == 1
        and len(runtime.requests) == count + 2
    )
    run = client.get(PREFIX + f"/workflow-runs/{results[0].json()['id']}").json()
    artifact = client.get(PREFIX + f"/outputs/{run['artifact_id']}").json()
    body = {
        "digest": artifact["digest"],
        "decision": "accepted",
        "reason": "Concurrent exact digest",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        reviews = [
            f.result(timeout=30)
            for f in [
                pool.submit(
                    client.post,
                    PREFIX + f"/workflow-runs/{run['id']}/review",
                    json=body,
                )
                for _ in range(2)
            ]
        ]
    assert all(r.status_code == 200 for r in reviews), [r.text for r in reviews]
    assert reviews[0].json() == reviews[1].json()


def test_revalidation_during_inference_and_durable_claim(workflow):
    client, db, runtime, _, saved, _ = workflow
    original = runtime.execute_direct_turn
    seen = False

    async def revoke(request, ctx):
        nonlocal seen
        with db.session() as s:
            state = json.loads(
                s.execute(
                    text(
                        "SELECT details_json FROM workflow_runs WHERE workflow_id=:id"
                    ),
                    {"id": saved["id"]},
                ).scalar()
            )
            task = next(t for t in state["tasks"] if t["node_id"] == "research")
            assert task["status"] == "running" and task["core_run_id"]
            assert (
                s.execute(
                    text(
                        "SELECT COUNT(*) FROM run_states WHERE id=:id AND execution_attestation IS NOT NULL"
                    ),
                    {"id": task["core_run_id"]},
                ).scalar()
                == 1
            )
        result = await original(request, ctx)
        with db.session(write=True) as s:
            OrganizationRepository(s).get_member(DEV_ORG, DEV_ACTOR).status = "inactive"
        seen = True
        return result

    runtime.execute_direct_turn = revoke
    client.post(
        PREFIX + f"/workflows/{saved['id']}/runs",
        json={
            "version_id": workflow[-1]["id"],
            "input": "Revocation",
            "idempotency_key": "revoked",
            "allow_remote_model": True,
        },
    )
    assert seen
    with db.session() as s:
        state = json.loads(
            s.execute(
                text("SELECT details_json FROM workflow_runs WHERE workflow_id=:id"),
                {"id": saved["id"]},
            ).scalar()
        )
        assert (
            state["status"] == "outcome_unknown"
            and state["tasks"][3]["status"] == "pending"
        )
        assert (
            s.execute(text("SELECT COUNT(*) FROM workflow_artifacts")).scalar() == 1
        )  # Input only; no revoked result emitted.


def test_actual_core_deadline_and_inflight_stop_do_not_advance(workflow):
    import asyncio

    client, db, runtime, app, _, _ = workflow
    original = runtime.execute_direct_turn

    async def stop_during_turn(request, ctx):
        with db.session() as s:
            id = s.execute(
                text("SELECT id FROM workflow_runs WHERE idempotency_key='active-stop'")
            ).scalar()
        stopped = await app.state.workflows.cancel(ctx, id)
        assert stopped["status"] == "outcome_unknown"
        return await original(request, ctx)

    runtime.execute_direct_turn = stop_during_turn
    count = len(runtime.requests)
    stopped = start(workflow, "active-stop")
    assert (
        stopped["status"] == "outcome_unknown"
        and stopped["error_code"] == "stop_unconfirmed"
    )
    assert len(runtime.requests) == count + 1
    assert stopped["tasks"][1]["output_artifact_id"] is None
    runtime.timeout = 0.05

    async def exceed_deadline(request, ctx):
        await asyncio.sleep(0.2)
        return await original(request, ctx)

    runtime.execute_direct_turn = exceed_deadline
    timed_out = start(workflow, "bounded-deadline")
    assert (
        timed_out["status"] == "outcome_unknown"
        and timed_out["tasks"][1]["output_artifact_id"] is None
    )
    with db.session() as s:
        assert (
            s.execute(
                text(
                    "SELECT COUNT(*) FROM run_states WHERE status='outcome_unknown' AND reserved_tokens>0"
                )
            ).scalar()
            == 1
        )
    artifact = client.get(PREFIX + f"/outputs/{stopped['artifact_id']}").json()
    assert artifact["task_id"] == "input"


def test_invalid_handoff_fails_consumer_before_dispatch(workflow, monkeypatch):
    from modules.core.history import HistoryUnverifiedError

    _, _, runtime, app, _, _ = workflow
    original = app.state.workflows.artifact
    read_count = 0

    def handoff(session, ctx, id):
        nonlocal read_count
        item, blob = original(session, ctx, id)
        if item.task_id == "research":
            read_count += 1
            if read_count > 1:
                raise HistoryUnverifiedError("synthetic corrupted handoff")
        return item, blob

    monkeypatch.setattr(app.state.workflows, "artifact", handoff)
    count = len(runtime.requests)
    run = start(workflow)
    assert run["status"] == "failed" and run["error_code"] == "handoff_rejected"
    assert len(runtime.requests) == count + 1
    tasks = {t["node_id"]: t for t in run["tasks"]}
    assert (
        tasks["handoff"]["status"] == "failed"
        and tasks["content"]["status"] == "pending"
    )


def test_stale_publication_authority_and_artifact_upload_not_supported(workflow):
    client, db, runtime, _, saved, version = workflow
    with db.engine.begin() as c:
        c.execute(
            text("UPDATE approvals SET payload_hash=:hash WHERE target_id=:id"),
            {"hash": "b" * 64, "id": version["graph"]["nodes"][1]["agent_version_id"]},
        )
    before = len(runtime.requests)
    response = client.post(
        PREFIX + f"/workflows/{saved['id']}/runs",
        json={
            "version_id": version["id"],
            "input": "Stale authority",
            "idempotency_key": "stale",
            "allow_remote_model": True,
        },
    )
    assert response.status_code != 200 and len(runtime.requests) == before
    assert (
        client.post(
            PREFIX + "/outputs",
            json={
                "mime": "application/json",
                "blob": "<script>bad()</script>",
                "path": "../../host-key",
            },
        ).status_code
        == 405
    )
