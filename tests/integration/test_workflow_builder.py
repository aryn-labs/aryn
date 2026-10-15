"""Workflow Studio adapter contracts over real Core and disposable storage."""
import asyncio
import copy
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager

import pytest
from httpx import Response
from database.connection import DatabaseManager
from database.repositories.organization_repo import OrganizationRepository
from modules.core.errors import sanitize
from modules.core.history import HistoryUnverifiedError
from services.api.studio import DEV_ORG, DEV_ACTOR

from tests.integration.test_studio_api import studio as studio, PREFIX, DEV_PROJECT
from tests.integration.test_workflow_execution import workflow as workflow, start


@pytest.mark.parametrize("graph", [dict(nodes=[], edges=[]), dict(nodes=[dict(id="agent", label="Agent", kind="agent")], edges=[])])
def test_editable_incomplete_drafts_cannot_be_frozen_or_executed(studio, graph):
    client, _, runtime, _ = studio
    before = len(runtime.requests)
    saved = client.post(PREFIX + "/workflows", json=dict(name="Incomplete draft", graph=graph, expected_revision=0))
    assert saved.status_code == 201, saved.text
    identifier = saved.json()["id"]
    assert client.get(PREFIX + "/workflows/" + identifier).json()["graph"]["nodes"] == saved.json()["graph"]["nodes"]
    rejected = client.post(PREFIX + f"/workflows/{identifier}/validate", json={})
    assert rejected.status_code == 422 and rejected.json()["error_code"] == "workflow_graph_rejected"
    assert client.post(PREFIX + f"/workflows/{identifier}/versions", json={"expected_revision": 1}).status_code == 422
    assert len(runtime.requests) == before


def test_search_literal_scope_and_revision_conflict(workflow):
    client, _, _, _, saved, _ = workflow
    definition = {k: saved[k] for k in ("name", "graph", "positions")}
    definition["name"] = "Literal %_ needle"
    item = client.post(PREFIX + "/workflows", json={**definition, "expected_revision": 0}).json()
    page = client.get(PREFIX + "/workflows", params={"q": "%_"}).json()
    assert [row["id"] for row in page["items"]] == [item["id"]]
    assert client.get(PREFIX + "/workflows", params={"q": "NEEDLE"}).json()["items"][0]["id"] == item["id"]
    assert client.get(PREFIX + "/workflows?q=x&q=y").status_code == 422
    assert client.post(PREFIX + f"/workflows/{item['id']}", json={**definition, "expected_revision": 1}).json()["revision"] == 2
    assert client.post(PREFIX + f"/workflows/{item['id']}", json={**definition, "expected_revision": 1}).status_code == 409
    assert client.get(PREFIX + "/workflows", params={"q": "not present"}).json() == {"items": [], "next": None}


def poll_run(client, identifier, phase):
    response = client.get(PREFIX + "/workflow-runs/" + identifier)
    try:
        body = response.json()
    except ValueError:
        body = {"message": "Non-JSON response body omitted"}
    credentials = getattr(client.app.state.workflows.db, "protected_credentials", ())
    # Only the public error envelope enters diagnostics, never prompts, outputs,
    # headers/cookies or arbitrary nested data returned by a failed dependency.
    public = {key: body[key] for key in ("error_code", "message", "correlation_id", "run_id") if isinstance(body, dict) and key in body}
    diagnostic = sanitize({"http_status": response.status_code, "phase": phase,
        "workflow_run_id": identifier, "body": public}, credentials=credentials)
    detail = json.dumps(diagnostic, ensure_ascii=True)[:2048]
    if response.status_code != 200 or not isinstance(body, dict) or "status" not in body:
        pytest.fail(detail, pytrace=False)
    return body


def finish(client, identifier):
    for _ in range(200):
        run = poll_run(client, identifier, "completion")
        if run["status"] != "running":
            return run
        time.sleep(0.01)
    pytest.fail("Core workflow did not finish")


def test_async_admission_real_checkpoint_and_idempotent_start(workflow):
    client, _, runtime, _, saved, version = workflow
    gate = asyncio.Event()
    original = runtime.execute_direct_turn

    async def held(request, context):
        await gate.wait()
        return await original(request, context)

    runtime.execute_direct_turn = held
    body = dict(version_id=version["id"], input="Actual isolated workflow input", idempotency_key="async-exact-request", allow_remote_model=True)
    url = PREFIX + f"/workflows/{saved['id']}/runs"
    response = client.post(url, json=body, headers={"Prefer": "respond-async"})
    assert response.status_code == 202 and response.headers["Preference-Applied"] == "respond-async"
    identifier = response.json()["id"]
    observed = None
    for _ in range(100):
        observed = poll_run(client, identifier, "admission_checkpoint")
        if any(t["core_run_id"] for t in observed["tasks"]):
            break
        time.sleep(0.01)
    tasks = {t["node_id"]: t for t in observed["tasks"]}
    assert tasks["research"]["status"] == "running" and tasks["research"]["core_run_id"]
    assert tasks["review"]["status"] == "pending"
    assert observed["traversed_edges"] == [version["graph"]["edges"][0]["id"]]
    assert client.post(url, json=body, headers={"Prefer": "respond-async"}).json()["id"] == identifier
    assert client.post(url, json={**body, "input": "different"}, headers={"Prefer": "respond-async"}).status_code == 409
    client.portal.call(gate.set)
    done = finish(client, identifier)
    assert done["status"] == "waiting_review"
    assert done["traversed_edges"] == [e["id"] for e in version["graph"]["edges"][:-1]]


@pytest.mark.parametrize("status", [401, 403, 409, 500, 200])
def test_polling_diagnostics_are_bounded_and_exclude_secrets(studio, monkeypatch, status):
    client, db, _, _ = studio
    secret = "synthetic-registered-diagnostic-secret"
    db.protected_credentials = (*db.protected_credentials, secret)
    response = Response(status, json={"error_code": "synthetic_failure", "message": f"Bearer fake-token {secret} " + "x" * 5000,
        "credential": "synthetic-hidden-credential", "output": "synthetic-private-output"})
    monkeypatch.setattr(client, "get", lambda *args: response)
    with pytest.raises(pytest.fail.Exception) as failure:
        poll_run(client, "workflow_run_synthetic", "completion")
    diagnostic = str(failure.value)
    assert len(diagnostic) <= 2048
    assert f'"http_status": {status}' in diagnostic and '"phase": "completion"' in diagnostic
    assert "synthetic_failure" in diagnostic and "workflow_run_synthetic" in diagnostic
    assert "[REDACTED]" in diagnostic
    assert all(value not in diagnostic for value in (secret, "fake-token", "synthetic-hidden-credential", "synthetic-private-output"))


@pytest.mark.parametrize("shared_manager", [False, True])
def test_workflow_read_during_live_commit_waits_for_verified_history(workflow, monkeypatch, shared_manager):
    client, db, _, _, _, _ = workflow
    run = start(workflow, "concurrent-review-read")
    artifact = client.get(PREFIX + "/outputs/" + run["artifact_id"]).json()
    prepared, release, reading = threading.Event(), threading.Event(), threading.Event()
    store = db.history_commitments
    original_prepare = store.prepare
    original_session = DatabaseManager(db.engine).session if shared_manager else db.session

    def held_prepare(*args):
        token = original_prepare(*args)
        prepared.set()
        assert release.wait(10), "Test did not release the live commit"
        return token

    @contextmanager
    def observed_session(write=False):
        if not write and prepared.is_set() and not release.is_set():
            reading.set()
        with original_session(write=write) as session:
            yield session

    monkeypatch.setattr(store, "prepare", held_prepare)
    monkeypatch.setattr(db, "session", observed_session)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(client.post, PREFIX + f"/workflow-runs/{run['id']}/review",
            json={"digest": artifact["digest"], "decision": "accepted", "reason": "Inspect isolated artifact"})
        try:
            assert prepared.wait(10), "Writer did not reach durable prepare"
            reader = pool.submit(poll_run, client, run["id"], "concurrent_commit")
            assert reading.wait(10), "Reader did not enter the workflow route"
            # A live commit is neither stale evidence nor an abandoned intent.
            # The reader must wait; it must not observe an unverified snapshot.
            with pytest.raises(FutureTimeout):
                reader.result(timeout=0.1)
        finally:
            release.set()
        assert writer.result(timeout=10).status_code == 200
        done = reader.result(timeout=10)
    assert done["status"] == "completed"
    assert all(task["status"] == "completed" for task in done["tasks"])
    assert [task["core_run_id"] for task in done["tasks"]] == [task["core_run_id"] for task in run["tasks"]]
    assert store.read()["pending"] is None


def test_workflow_abandoned_commit_still_fails_closed(workflow, monkeypatch):
    client, db, _, _, _, _ = workflow
    run = start(workflow, "abandoned-review-commit")
    artifact = client.get(PREFIX + "/outputs/" + run["artifact_id"]).json()

    def failed_ack(token):
        raise OSError("Synthetic failure after DB commit before commitment ACK")

    monkeypatch.setattr(db.history_commitments, "finish", failed_ack)
    response = client.post(PREFIX + f"/workflow-runs/{run['id']}/review",
        json={"digest": artifact["digest"], "decision": "accepted", "reason": "Inspect isolated artifact"})
    assert response.status_code == 500 and response.json()["error_code"] == "execution_failed"
    response = client.get(PREFIX + f"/workflow-runs/{run['id']}")
    assert response.status_code == 409 and response.json()["error_code"] == "http_409"
    with pytest.raises(HistoryUnverifiedError, match="unresolved"):
        db.history_commitments.read()


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_scoped_review_receipt_exact_digest_and_recorded_terminal_edge(workflow, decision):
    client, _, _, _, _, version = workflow
    run = start(workflow, "receipt-" + decision)
    artifact = client.get(PREFIX + "/outputs/" + run["artifact_id"]).json()
    url = PREFIX + f"/workflow-runs/{run['id']}/review"
    assert client.get(url).status_code == 404
    body = dict(digest=artifact["digest"], decision=decision, reason="Inspect exact artifact")
    assert client.post(url, json={**body, "digest": "0" * 64}).status_code == 409
    receipt = client.post(url, json=body)
    assert receipt.status_code == 200
    assert client.get(url).json() == receipt.json()
    assert client.get(url.replace(DEV_PROJECT, "foreign-project")).status_code in (403, 404)
    done = client.get(PREFIX + f"/workflow-runs/{run['id']}").json()
    terminal_edge = version["graph"]["edges"][-1]["id"]
    assert (terminal_edge in done["traversed_edges"]) == (decision == "accepted")
    assert client.post(url, json={**body, "decision": "accepted" if decision == "rejected" else "rejected"}).status_code == 409


def test_draft_can_hold_unconfigured_agent_but_preserves_executable_contract(workflow):
    client, _, _, _, saved, version = workflow
    body = {k: copy.deepcopy(saved[k]) for k in ("name", "graph", "positions")}
    body["graph"]["nodes"][1]["assignment_id"] = None
    body["graph"]["nodes"][1]["agent_version_id"] = None
    response = client.post(PREFIX + f"/workflows/{saved['id']}", json={**body, "expected_revision": 1})
    assert response.status_code == 200
    assert client.post(PREFIX + f"/workflows/{saved['id']}/versions", json={"expected_revision": 2}).status_code == 422
    assert client.get(PREFIX + "/workflow-versions/" + version["id"]).json() == version


def test_async_start_keeps_csrf_and_membership_authority(workflow):
    client, db, runtime, _, saved, version = workflow
    before = len(runtime.requests)
    body = dict(version_id=version["id"], input="No unauthorized inference", idempotency_key="denied-async", allow_remote_model=True)
    url = PREFIX + f"/workflows/{saved['id']}/runs"
    assert client.post(url, json=body, headers={"Prefer": "respond-async", "X-CSRF-Token": "invalid"}).status_code == 403
    with db.session(write=True) as session:
        OrganizationRepository(session).get_member(DEV_ORG, DEV_ACTOR).role = "viewer"
    assert client.post(url, json=body, headers={"Prefer": "respond-async"}).status_code == 403
    assert len(runtime.requests) == before


def test_governed_targets_are_scoped_paginated_and_do_not_disclose_agent_configuration(workflow):
    client, _, runtime, _, _, _ = workflow
    before = len(runtime.requests)
    first = client.get(PREFIX + "/workflow-targets?limit=1")
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 1 and page["items"][0]["eligible"] and page["next"]
    assert page["permissions"]["run:create"]
    assert set(page["items"][0]) == {"id", "blueprint_id", "version_id", "name", "role_name", "version_number", "model", "eligible", "reason"}
    second = client.get(PREFIX + "/workflow-targets", params={"limit": 1, "after": page["next"]}).json()
    assert len(second["items"]) == 1 and second["items"][0]["id"] != page["items"][0]["id"]
    item = page["items"][0]
    assert client.get(PREFIX + "/workflow-targets/" + item["id"]).json()["items"] == [item]
    assert client.get(PREFIX + "/workflow-targets?limit=1&limit=2").status_code == 422
    assert client.get(PREFIX + "/workflow-targets?unknown=x").status_code == 422
    assert client.get(PREFIX + "/workflow-targets?after=foreign-assignment").status_code == 404
    assert client.get(PREFIX.replace(DEV_PROJECT, "foreign-project") + "/workflow-targets/" + item["id"]).status_code in (403, 404)
    assert len(runtime.requests) == before


def test_target_eligibility_uses_the_same_core_pin_admission(workflow):
    from database.schema import AgentAssignmentModel
    client, db, _, _, saved, version = workflow
    assignment_id = version["graph"]["nodes"][1]["assignment_id"]
    with db.session(write=True) as session:
        session.get(AgentAssignmentModel, assignment_id).status = "inactive"
    item = client.get(PREFIX + "/workflow-targets/" + assignment_id).json()["items"][0]
    assert item["eligible"] is False and item["reason"] == "assignment_pin_changed"
    rejected = client.post(PREFIX + f"/workflows/{saved['id']}/validate", json={})
    assert rejected.status_code == 422 and rejected.json()["issues"][0]["code"] == item["reason"]


def test_workflow_start_refreshes_gateway_catalog_after_api_restart(workflow):
    _, _, _, app, _, _ = workflow
    app.state.coordinator.model_router.replace_catalog([])
    assert start(workflow, "cold-gateway-catalog")["status"] == "waiting_review"


def test_failed_discovery_blocks_workflow_before_inference(workflow):
    from packages.contracts.runtime import GatewayDiscovery
    client, _, runtime, _, saved, version = workflow
    before = len(runtime.requests)

    async def unavailable(**kwargs):
        return GatewayDiscovery()

    runtime.discover_models = unavailable
    response = client.post(PREFIX + f"/workflows/{saved['id']}/runs", json=dict(version_id=version["id"], input="Do not dispatch", idempotency_key="gateway-discovery-denied", allow_remote_model=True), headers={"Prefer": "respond-async"})
    assert response.status_code == 503
    assert len(runtime.requests) == before
    assert client.get(PREFIX + f"/workflows/{saved['id']}/runs").json()["items"] == []


@pytest.mark.parametrize("kind", ["agent", "condition"])
def test_html_consumers_can_be_edited_but_cannot_pass_text_only_runtime_admission(workflow, kind):
    from packages.contracts.workflow import Graph

    client, _, runtime, _, saved, version = workflow
    before = len(runtime.requests)
    body = {k: copy.deepcopy(saved[k]) for k in ("name", "graph", "positions")}
    graph = body["graph"]
    consumer = dict(id="html_consumer", label="Unsupported HTML consumer", kind=kind, input_schema="website", output_schema="website")
    if kind == "agent":
        consumer.update(output_schema="text", assignment_id=graph["nodes"][1]["assignment_id"], agent_version_id=graph["nodes"][1]["agent_version_id"])
        for node in graph["nodes"]:
            if node["kind"] in ("review", "end"):
                node.update(input_schema="text", output_schema="text")
    else:
        consumer["predicate"] = dict(operator="nonempty", literal="")
    graph["nodes"].insert(-2, consumer)
    for edge in graph["edges"]:
        if edge["source"] == "website":
            edge["target"] = consumer["id"]
    ports = ["value"] if kind == "agent" else ["yes", "no"]
    graph["edges"].extend(dict(id="html_" + port, source=consumer["id"], target="review", source_port=port) for port in ports)
    # Historical graph parsing stays compatible; executable admission owns the restriction.
    Graph.model_validate(graph)
    response = client.post(PREFIX + f"/workflows/{saved['id']}", json={**body, "expected_revision": 1})
    assert response.status_code == 200, response.text
    for suffix, request in (("validate", {}), ("versions", {"expected_revision": 2})):
        rejected = client.post(PREFIX + f"/workflows/{saved['id']}/{suffix}", json=request)
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["issues"] == [{"subject": "html_consumer", "code": "text_envelope_required"}]
    assert len(runtime.requests) == before
    assert client.get(PREFIX + "/workflow-versions/" + version["id"]).json() == version
