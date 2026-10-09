"""Actual scoped Brief/Relay/Bench path and adversarial recovery boundaries."""

import json
import pytest
from sqlalchemy import text
from tests.integration.test_studio_api import studio as studio, PREFIX
from tests.integration.test_workflow_execution import workflow as workflow, start


def post(client, path, body=None):
    response = client.post(PREFIX + path, json={} if body is None else body)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def demo_incident(client, blocking_fault=False, key="service-stopped"):
    created = post(client, "/relay/demo-fixtures", {"name": "Disposable API worker"})
    target = created["fixture"]
    stopped = post(
        client,
        "/relay/demo-fixtures/" + target["id"],
        {
            "expected_revision": target["revision"],
            "running": False,
            "blocking_fault": blocking_fault,
        },
    )
    incident = post(
        client,
        "/relay/signals",
        {"target_id": target["id"], "dedup_key": key, "severity": "high"},
    )
    return created, stopped, incident


def investigated(client, incident, sources=None):
    body = {"expected_revision": incident["revision"]}
    if sources is not None:
        body["source_ids"] = sources
    return post(client, f"/relay/{incident['id']}/investigate", body)


def proposed(client, incident):
    return post(
        client,
        f"/relay/{incident['id']}/proposals",
        {
            "expected_revision": incident["revision"],
            "action": "restart_demo",
            "target_id": incident["target_id"],
            "target_revision": incident["fixture"]["revision"],
            "bundle_id": incident["bundle_id"],
            "reason": "Restart only the verified disposable service; keep conflicting evidence.",
        },
    )


def approved(client, incident):
    return post(
        client,
        f"/relay/{incident['id']}/approve",
        {
            "payload_hash": incident["proposal"]["payload_hash"],
            "reason": "Human review of exact isolated action and independent health gate.",
        },
    )


def execution_body(incident, key="fixed-recovery"):
    return {
        "proposal_id": incident["proposal"]["id"],
        "payload_hash": incident["proposal"]["payload_hash"],
        "idempotency_key": key,
    }


def test_real_evidence_recovery_capsule_replay_has_no_live_effects(studio, monkeypatch):
    client, db, runtime, app = studio
    created, _, incident = demo_incident(client)
    repeated = post(
        client,
        "/relay/signals",
        {
            "target_id": incident["target_id"],
            "dedup_key": "service-stopped",
            "severity": "high",
        },
    )
    assert repeated["id"] == incident["id"]
    incident = investigated(client, incident)
    assert incident["status"] == "INVESTIGATING"
    bundle = incident["bundle"]
    assert bundle["evaluation"]["status"] == "CONFLICTING"
    assert {item["relationship"] for item in bundle["evaluation"]["items"]} == {
        "support",
        "conflict",
    }
    assert all(
        item["integrity"] == "VERIFIED" for item in bundle["evaluation"]["items"]
    )
    incident = proposed(client, incident)
    receipt = approved(client, incident)
    assert (
        receipt["target_type"] == "relay_action"
        and receipt["payload_hash"] == incident["proposal"]["payload_hash"]
    )
    request = execution_body(incident)
    incident = post(client, f"/relay/{incident['id']}/execute", request)
    assert incident["status"] == "RECOVERED", incident
    assert (
        incident["execution"]["status"] == "verified"
        and incident["verification"]["recovered"] is True
    )
    assert incident["fixture"]["revision"] == created["fixture"]["revision"] + 2
    assert (
        post(client, f"/relay/{incident['id']}/execute", request)["revision"]
        == incident["revision"]
    )
    incident = post(
        client,
        f"/relay/{incident['id']}/close",
        {"expected_revision": incident["revision"]},
    )
    assert incident["status"] == "CLOSED" and incident["capsule"]["snapshot"] == {
        "running": False,
        "blocking_fault": False,
    }
    calls = len(runtime.requests)

    def forbidden(*args, **kwargs):
        raise AssertionError("Replay attempted a live recovery write.")

    monkeypatch.setattr(app.state.relay.executor, "apply", forbidden)
    replay = post(client, f"/bench/capsules/{incident['capsule_id']}/replay")
    assert replay["passed"] is True, replay
    assert (
        replay["live_write_calls"] == 0
        and replay["model"] is None
        and replay["provider"] is None
    )
    assert replay["promotion_evidence"] is False and len(runtime.requests) == calls
    assert all(item["passed"] for item in replay["graders"])
    downloaded = client.get(
        PREFIX + f"/relay/capsules/{incident['capsule_id']}/download"
    )
    assert (
        downloaded.status_code == 200
        and downloaded.headers["x-content-type-options"] == "nosniff"
    )
    assert json.loads(downloaded.content)["digest"] == incident["capsule"]["digest"]
    with db.session() as session:
        assert (
            session.execute(text("SELECT COUNT(*) FROM relay_incidents")).scalar() == 1
        )
        assert (
            session.execute(text("SELECT COUNT(*) FROM relay_executions")).scalar() == 1
        )
        assert (
            session.execute(text("SELECT COUNT(*) FROM relay_capsules")).scalar() == 1
        )


def test_action_completed_is_not_recovered_when_health_still_fails(studio):
    client, _, _, _ = studio
    _, _, incident = demo_incident(client, blocking_fault=True)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)
    incident = post(
        client, f"/relay/{incident['id']}/execute", execution_body(incident)
    )
    assert (
        incident["status"] == "DEGRADED"
        and incident["execution"]["status"] == "health_failed"
    )
    assert (
        incident["fixture"]["running"] is True
        and incident["verification"]["recovered"] is False
    )
    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/close",
            json={"expected_revision": incident["revision"]},
        ).status_code
        == 409
    )
    assert incident["capsule_id"] is None


def test_no_evidence_abstains_and_cannot_propose(studio):
    client, _, _, _ = studio
    _, _, incident = demo_incident(client)
    incident = investigated(client, incident, [])
    assert incident["bundle"]["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert (
        incident["bundle"]["evaluation"]["items"] == []
        and incident["bundle"]["evaluation"]["abstention"]
    )
    response = client.post(
        PREFIX + f"/relay/{incident['id']}/proposals",
        json={
            "expected_revision": incident["revision"],
            "target_id": incident["target_id"],
            "target_revision": incident["fixture"]["revision"],
            "bundle_id": incident["bundle_id"],
            "reason": "Unsupported guess",
        },
    )
    assert response.status_code == 409


def test_verified_document_search_not_found_and_empty_coverage(studio):
    client, _, _, _ = studio
    document = post(
        client,
        "/brief/documents",
        {
            "title": "Disposable procedure",
            "text": "Restart the demo worker after human approval.",
        },
    )
    bundle = post(
        client,
        "/brief",
        {
            "title": "Procedure search",
            "source_ids": [document["source"]["id"]],
            "hypothesis": {
                "question": "Does the procedure describe approval?",
                "predicate": "contains_text",
                "text": "approval",
            },
        },
    )
    assert bundle["evaluation"]["status"] == "SUPPORTED"
    missing = post(
        client,
        "/brief",
        {
            "title": "Missing procedure",
            "source_ids": [document["source"]["id"]],
            "hypothesis": {
                "question": "Does it mention public deploy?",
                "predicate": "contains_text",
                "text": "public deploy",
            },
        },
    )
    assert (
        missing["evaluation"]["status"] == "NOT_FOUND"
        and missing["evaluation"]["abstention"]
    )
    low = post(
        client,
        "/brief",
        {
            "title": "Low coverage",
            "source_ids": [document["source"]["id"]],
            "hypothesis": {
                "question": "Need two independent snapshots",
                "predicate": "contains_text",
                "text": "approval",
                "minimum_sources": 2,
            },
        },
    )
    assert low["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize("attack", ["blob", "mime", "document", "missing"])
def test_changed_source_is_unverified_and_cannot_support_claim(studio, attack):
    client, db, _, _ = studio
    document = post(
        client,
        "/brief/documents",
        {"title": "Scoped demo evidence", "text": "approved recovery procedure"},
    )
    bundle = post(
        client,
        "/brief",
        {
            "title": "Verified literal",
            "source_ids": [document["source"]["id"]],
            "hypothesis": {
                "question": "Contains approved?",
                "predicate": "contains_text",
                "text": "approved",
            },
        },
    )
    assert bundle["evaluation"]["status"] == "SUPPORTED"
    with db.engine.begin() as connection:
        if attack == "document":
            connection.execute(text("DROP TRIGGER aryn_evidence_documents_update"))
            connection.execute(
                text(
                    "UPDATE evidence_documents SET details_json=replace(details_json,'approved','forged') WHERE id=:id"
                ),
                {"id": document["document"]["id"]},
            )
        elif attack == "missing":
            connection.execute(text("DROP TRIGGER aryn_evidence_sources_delete"))
            connection.execute(
                text("DELETE FROM evidence_sources WHERE id=:id"),
                {"id": document["source"]["id"]},
            )
        else:
            connection.execute(text("DROP TRIGGER aryn_evidence_sources_update"))
            if attack == "blob":
                connection.execute(
                    text("UPDATE evidence_sources SET blob=:blob WHERE id=:id"),
                    {"blob": b"{}", "id": document["source"]["id"]},
                )
            else:
                connection.execute(
                    text(
                        "UPDATE evidence_sources SET details_json=replace(details_json,'application/json','text/html') WHERE id=:id"
                    ),
                    {"id": document["source"]["id"]},
                )
    response = client.get(PREFIX + "/brief/" + bundle["id"])
    assert response.status_code == 200
    evaluation = response.json()["evaluation"]
    assert evaluation["status"] == "INSUFFICIENT_EVIDENCE" and evaluation["abstention"]
    assert (
        evaluation["items"][0]["integrity"] == "UNVERIFIED"
        and evaluation["items"][0]["excerpt"] == ""
    )


def test_two_wrappers_of_same_origin_do_not_inflate_coverage(studio):
    client, _, _, _ = studio
    document = post(
        client, "/brief/documents", {"title": "One origin", "text": "approval"}
    )
    second = post(
        client,
        "/brief/sources",
        {
            "title": "Another wrapper",
            "source_ref": {"kind": "document", "id": document["document"]["id"]},
        },
    )
    bundle = post(
        client,
        "/brief",
        {
            "title": "Duplicate origin coverage",
            "source_ids": [document["source"]["id"], second["id"]],
            "hypothesis": {
                "question": "Need independent source snapshots",
                "predicate": "contains_text",
                "text": "approval",
                "minimum_sources": 2,
            },
        },
    )
    assert (
        bundle["evaluation"]["coverage"] == 1
        and bundle["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    )


def test_stale_sources_abstain_without_fabricating_freshness(studio, monkeypatch):
    import datetime
    from types import SimpleNamespace
    from modules.brief import service

    client, _, _, _ = studio
    document = post(
        client,
        "/brief/documents",
        {"title": "Historical procedure", "text": "approval"},
    )
    bundle = post(
        client,
        "/brief",
        {
            "title": "Freshness gate",
            "source_ids": [document["source"]["id"]],
            "hypothesis": {
                "question": "Current procedure?",
                "predicate": "contains_text",
                "text": "approval",
            },
        },
    )

    class FutureClock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime.now(tz) + datetime.timedelta(days=8)

    monkeypatch.setattr(
        service,
        "datetime",
        SimpleNamespace(datetime=FutureClock, timezone=datetime.timezone),
    )
    current = client.get(PREFIX + "/brief/" + bundle["id"]).json()
    assert current["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert current["evaluation"]["items"][0]["freshness"] == "stale"
    assert current["evaluation"]["items"][0]["integrity"] == "VERIFIED"


@pytest.mark.parametrize(
    "attack", ["unapproved", "changed_hash", "changed_proposal", "target_revision"]
)
def test_unapproved_or_stale_actions_do_not_mutate_demo(studio, attack):
    client, db, _, _ = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    body = execution_body(incident)
    if attack != "unapproved":
        approved(client, incident)
    if attack == "changed_hash":
        body["payload_hash"] = "f" * 64
    elif attack == "changed_proposal":
        incident = proposed(client, incident)
        body = execution_body(incident)
    elif attack == "target_revision":
        post(
            client,
            "/relay/demo-fixtures/" + incident["target_id"],
            {
                "expected_revision": incident["fixture"]["revision"],
                "running": False,
                "blocking_fault": True,
            },
        )
    response = client.post(PREFIX + f"/relay/{incident['id']}/execute", json=body)
    assert response.status_code in {403, 409}, response.text
    with db.session() as session:
        assert (
            session.execute(text("SELECT COUNT(*) FROM relay_executions")).scalar() == 0
        )
    current = client.get(PREFIX + f"/relay/{incident['id']}").json()
    assert current["fixture"]["running"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"source_ref": {"kind": "url", "id": "https://private"}, "title": "Untrusted"},
        {
            "source_ref": {"kind": "artifact", "id": "../server.key"},
            "title": "Traversal",
        },
        {
            "source_ref": {"kind": "run", "id": "missing"},
            "title": "Invented",
            "digest": "0" * 64,
        },
    ],
)
def test_ingestion_does_not_trust_client_references_or_hashes(studio, payload):
    client, db, _, _ = studio
    assert client.post(PREFIX + "/brief/sources", json=payload).status_code == 422
    with db.session() as session:
        assert (
            session.execute(text("SELECT COUNT(*) FROM evidence_sources")).scalar() == 0
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"command": "rm -rf /"},
        {"action": "shell"},
        {"parameters": {"path": "../../customer"}},
        {"target_id": "https://production"},
    ],
)
def test_proposal_cannot_escape_fixed_disposable_action(studio, extra):
    client, _, _, _ = studio
    _, _, incident = demo_incident(client)
    incident = investigated(client, incident)
    body = {
        "expected_revision": incident["revision"],
        "target_id": incident["target_id"],
        "target_revision": incident["fixture"]["revision"],
        "bundle_id": incident["bundle_id"],
        "reason": "Unsafe action",
    }
    body.update(extra)
    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/proposals", json=body
        ).status_code
        == 422
    )


def test_demo_executor_denial_does_not_claim_recovery(studio, monkeypatch):
    from database.repositories.exceptions import InvalidStateTransitionError

    client, _, _, app = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)

    def denied(*args):
        raise InvalidStateTransitionError("Disposable precondition was denied.")

    monkeypatch.setattr(app.state.relay.executor, "apply", denied)
    current = post(client, f"/relay/{incident['id']}/execute", execution_body(incident))
    assert (
        current["status"] == "DEGRADED" and current["execution"]["status"] == "denied"
    )
    assert current["verification"] is None and current["fixture"]["running"] is False


def test_lost_verification_requires_explicit_reconciliation_not_retry(
    studio, monkeypatch
):
    client, _, _, app = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)
    verify = app.state.relay.verify

    def unavailable(*args, **kwargs):
        raise OSError("Health observation unavailable.")

    monkeypatch.setattr(app.state.relay, "verify", unavailable)
    body = execution_body(incident)
    current = post(client, f"/relay/{incident['id']}/execute", body)
    assert (
        current["status"] == "OUTCOME_UNKNOWN" and current["fixture"]["running"] is True
    )
    assert (
        post(client, f"/relay/{incident['id']}/execute", body)["fixture"]["revision"]
        == current["fixture"]["revision"]
    )
    monkeypatch.setattr(app.state.relay, "verify", verify)
    current = post(
        client,
        f"/relay/{incident['id']}/reconcile",
        {"expected_revision": current["revision"]},
    )
    assert current["status"] == "RECOVERED" and current["verification"]["recovered"]


def test_revocation_between_claim_and_effect_is_denied_at_commit(studio, monkeypatch):
    client, db, _, app = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)
    apply = app.state.relay.executor.apply

    def revoke(ctx, identifier):
        with db.session(write=True) as session:
            session.execute(text("UPDATE memberships SET role='viewer'"))
        return apply(ctx, identifier)

    monkeypatch.setattr(app.state.relay.executor, "apply", revoke)
    response = client.post(
        PREFIX + f"/relay/{incident['id']}/execute", json=execution_body(incident)
    )
    assert response.status_code == 403, response.text
    # Revocation removes project visibility as well as mutation authority.
    with db.session(write=True) as session:
        session.execute(text("UPDATE memberships SET role='admin'"))
    current = client.get(PREFIX + f"/relay/{incident['id']}").json()
    assert (
        current["status"] == "DEGRADED" and current["execution"]["status"] == "denied"
    )
    assert current["fixture"]["running"] is False


def test_incident_key_and_execution_claim_are_exactly_once_under_contention(
    studio, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    client, db, _, app = studio
    created = post(client, "/relay/demo-fixtures", {"name": "Contention demo"})
    target = created["fixture"]
    post(
        client,
        "/relay/demo-fixtures/" + target["id"],
        {"expected_revision": 1, "running": False, "blocking_fault": False},
    )
    with ThreadPoolExecutor(4) as pool:
        responses = list(
            pool.map(
                lambda _: post(
                    client,
                    "/relay/signals",
                    {
                        "target_id": target["id"],
                        "dedup_key": "race",
                        "severity": "medium",
                    },
                ),
                range(4),
            )
        )
    assert len({item["id"] for item in responses}) == 1
    incident = proposed(client, investigated(client, responses[0]))
    approved(client, incident)
    entered, release = threading.Event(), threading.Event()
    apply = app.state.relay.executor.apply
    calls = []

    def held(ctx, identifier):
        calls.append(identifier)
        entered.set()
        assert release.wait(10)
        return apply(ctx, identifier)

    monkeypatch.setattr(app.state.relay.executor, "apply", held)
    body = execution_body(incident)
    from packages.contracts.intelligence import ExecuteAction
    from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT

    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)

    def execute():
        return app.state.relay.execute(ctx, incident["id"], ExecuteAction(**body))

    with ThreadPoolExecutor(2) as pool:
        # HTTP mutations retain the existing global lock. Independently exercise
        # competing Core service admissions against the durable database claim.
        first = pool.submit(execute)
        assert entered.wait(10)
        second = pool.submit(execute).result(timeout=10)
        assert second["status"] == "EXECUTING"
        release.set()
        assert first.result(timeout=10)["status"] == "RECOVERED"
    assert len(calls) == 1
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM relay_signals")).scalar() == 1
        assert (
            session.execute(text("SELECT COUNT(*) FROM relay_executions")).scalar() == 1
        )


def test_real_core_run_and_artifact_sources_keep_exact_workflow_lineage(workflow):
    client, db, _, _, saved, _ = workflow
    run = start(workflow)
    core_run = next(
        t["core_run_id"] for t in run["tasks"] if t["node_id"] == "research"
    )
    sources = [
        post(
            client,
            "/brief/sources",
            {
                "title": "Authorized internal " + kind,
                "source_ref": {"kind": kind, "id": identifier},
            },
        )
        for kind, identifier in (("run", core_run), ("artifact", run["artifact_id"]))
    ]
    bundle = post(
        client,
        "/brief",
        {
            "title": "Actual workflow evidence",
            "workflow_run_id": run["id"],
            "hypothesis": {
                "question": "Did the research task complete?",
                "predicate": "run_completed",
            },
            "source_ids": [s["id"] for s in sources],
        },
    )
    assert bundle["evaluation"]["status"] == "SUPPORTED"
    assert (
        bundle["workflow"]["id"] == run["id"]
        and bundle["workflow"]["workflow_id"] == saved["id"]
    )
    for kind, identifier in (
        ("run", core_run),
        ("artifact", run["artifact_id"]),
        ("workflow_run", run["id"]),
    ):
        response = client.get(
            PREFIX + "/brief-links", params={"kind": kind, "id": identifier}
        )
        assert (
            response.status_code == 200
            and response.json()["items"][0]["id"] == bundle["id"]
        )
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM workflow_runs")).scalar() == 1


@pytest.mark.parametrize("checkpoint", ["before_effect", "after_effect"])
def test_crash_recovery_retains_unknown_without_repeating_effect(
    studio, monkeypatch, checkpoint
):
    from database.connection import DatabaseManager, create_db_engine
    from fastapi.testclient import TestClient
    from services.api.studio import create_app, DEV_ACTOR, DEV_ORG, DEV_PROJECT
    from tests.integration.test_studio_api import ORIGIN
    from packages.contracts.intelligence import ExecuteAction
    from modules.core.workflows.ownership import ExecutionOwnershipError

    client, db, runtime, app = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)
    apply = app.state.relay.executor.apply

    class ProcessLoss(BaseException):
        pass

    def crash(ctx, identifier):
        if checkpoint == "after_effect":
            apply(ctx, identifier)
        raise ProcessLoss()

    monkeypatch.setattr(app.state.relay.executor, "apply", crash)
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    body = ExecuteAction(**execution_body(incident))
    with pytest.raises(ProcessLoss):
        app.state.relay.execute(ctx, incident["id"], body)
    db.engine.dispose()
    reopened = DatabaseManager(
        create_db_engine(db.engine.url.render_as_string(hide_password=False))
    )
    new_app = None
    try:
        new_app = create_app(reopened, runtime, testing=True)
        with TestClient(new_app, base_url=ORIGIN, client=("127.0.0.1", 1)) as other:
            csrf = other.post(
                "/api/session", json={}, headers={"Origin": ORIGIN}
            ).json()["csrf"]
            other.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
            current = other.get(PREFIX + f"/relay/{incident['id']}").json()
            assert current["status"] == "OUTCOME_UNKNOWN"
            assert current["fixture"]["running"] is (checkpoint == "after_effect")
            assert (
                post(other, f"/relay/{incident['id']}/execute", body.model_dump())[
                    "fixture"
                ]["revision"]
                == current["fixture"]["revision"]
            )
            current = post(
                other,
                f"/relay/{incident['id']}/reconcile",
                {"expected_revision": current["revision"]},
            )
            assert current["status"] == (
                "RECOVERED" if checkpoint == "after_effect" else "DEGRADED"
            )
        with pytest.raises(ExecutionOwnershipError):
            app.state.coordinator._fence()
    finally:
        if new_app is not None:
            new_app.state.coordinator.authority.close()
        reopened.engine.dispose()


def test_scoped_access_pagination_and_viewer_cannot_authorize_recovery(studio):
    from database.repositories.organization_repo import OrganizationRepository
    from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT

    client, db, _, app = studio
    with db.session(write=True) as session:
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
        OrganizationRepository(session).create_project(
            ctx, "proj_studio_operations", "Other project", "other-project"
        )
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    bundle = incident["bundle"]
    other = "/api/projects/proj_studio_operations"
    for path in (
        f"/brief/{bundle['id']}",
        f"/relay/{incident['id']}",
        f"/brief/sources/{bundle['source_ids'][0]}",
    ):
        assert client.get(other + path).status_code == 404
    assert (
        client.post(
            other + f"/relay/{incident['id']}/execute", json=execution_body(incident)
        ).status_code
        == 404
    )
    assert client.get(PREFIX + "/brief?limit=101").status_code == 422
    assert client.get(PREFIX + "/relay?status=UNKNOWN&status=CLOSED").status_code == 422
    # Core viewer membership allows project reads but never approval or execution.
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.get_member(DEV_ORG, DEV_ACTOR).role = "viewer"
        repo.add_project_member(DEV_PROJECT, DEV_ACTOR, "viewer")
    assert client.get(PREFIX + f"/relay/{incident['id']}").status_code == 200
    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/approve",
            json={
                "payload_hash": incident["proposal"]["payload_hash"],
                "reason": "Not authorized",
            },
        ).status_code
        == 403
    )

    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/execute", json=execution_body(incident)
        ).status_code
        == 403
    )


def test_signed_approval_corruption_cannot_authorize_action(studio):
    client, db, _, _ = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    receipt = approved(client, incident)
    with db.engine.begin() as connection:
        connection.execute(
            text("UPDATE approvals SET attestation=:bad WHERE id=:id"),
            {"bad": "f" * 64, "id": receipt["approval_id"]},
        )
    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/execute", json=execution_body(incident)
        ).status_code
        == 409
    )
    current = client.get(PREFIX + f"/relay/{incident['id']}").json()
    assert current["approval"] is None and current["fixture"]["running"] is False
    with db.session() as session:
        assert (
            session.execute(text("SELECT COUNT(*) FROM relay_executions")).scalar() == 0
        )


def test_changed_health_after_verification_cannot_close(studio):
    client, _, _, _ = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)
    recovered = post(
        client, f"/relay/{incident['id']}/execute", execution_body(incident)
    )
    post(
        client,
        "/relay/demo-fixtures/" + incident["target_id"],
        {
            "expected_revision": recovered["fixture"]["revision"],
            "running": False,
            "blocking_fault": False,
        },
    )
    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/close",
            json={"expected_revision": recovered["revision"]},
        ).status_code
        == 409
    )


def test_replay_graders_reject_escaped_adapter_and_never_write_live(
    studio, monkeypatch
):
    from modules.bench.replay import InMemoryRecoveryReplay
    from packages.contracts.bench import ActionEvidence

    client, _, _, app = studio
    _, _, incident = demo_incident(client)
    incident = proposed(client, investigated(client, incident))
    approved(client, incident)
    incident = post(
        client, f"/relay/{incident['id']}/execute", execution_body(incident)
    )
    incident = post(
        client,
        f"/relay/{incident['id']}/close",
        {"expected_revision": incident["revision"]},
    )
    before = incident["fixture"]

    def escaped(self, snapshot):
        return {
            "running": True,
            "blocking_fault": False,
            "recovered": True,
            "operation_count": 1,
        }, [
            ActionEvidence(
                action_id="unsafe", action="live_recovery", capability="host_access"
            )
        ]

    monkeypatch.setattr(InMemoryRecoveryReplay, "replay", escaped)

    def forbidden(*args, **kwargs):
        raise AssertionError("Diagnostic invoked live executor")

    monkeypatch.setattr(app.state.relay.executor, "apply", forbidden)
    replay = post(client, f"/bench/capsules/{incident['capsule_id']}/replay")
    assert replay["passed"] is False and replay["promotion_evidence"] is False
    assert any(not g["passed"] for g in replay["graders"])
    assert client.get(PREFIX + f"/relay/{incident['id']}").json()["fixture"] == before
    assert (
        client.post(
            PREFIX + f"/bench/capsules/{incident['capsule_id']}/replay",
            json={"command": "host command"},
        ).status_code
        == 422
    )


def test_other_disposable_targets_cannot_inflate_incident_coverage(studio):
    client, _, _, _ = studio
    _, stopped, incident = demo_incident(client)
    other = post(
        client, "/relay/demo-fixtures", {"name": "Different disposable target"}
    )
    investigated_state = investigated(
        client, incident, [stopped["source"]["id"], other["source"]["id"]]
    )
    evaluation = investigated_state["bundle"]["evaluation"]
    assert (
        evaluation["status"] == "INSUFFICIENT_EVIDENCE" and evaluation["coverage"] == 1
    )
    assert {i["relationship"] for i in evaluation["items"]} == {"conflict", "neutral"}
    assert (
        client.post(
            PREFIX + f"/relay/{incident['id']}/proposals",
            json={
                "expected_revision": investigated_state["revision"],
                "target_id": incident["target_id"],
                "target_revision": investigated_state["fixture"]["revision"],
                "bundle_id": investigated_state["bundle_id"],
                "reason": "Different target cannot authorize",
            },
        ).status_code
        == 409
    )


def test_new_sqlite_guards_prevent_history_rewrite_and_populated_rollback(studio):
    from sqlalchemy.exc import DBAPIError
    from database.intelligence_protection import TABLES, MUTABLE_TABLES
    from tests.postgresql.conftest import migrate_to

    client, db, _, _ = studio
    demo_incident(client)
    for table in TABLES:
        # Empty tables still have immutable update/delete triggers, verified by
        # schema inspection; populated rows exercise their actual enforcement.
        with db.engine.connect() as connection:
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name=:name"
                    ),
                    {"name": f"aryn_{table}_update"},
                ).scalar()
                == 1
            )
        if count:
            for statement in (
                f"UPDATE {table} SET details_json='{{}}'",
                f"DELETE FROM {table}",
            ):
                with pytest.raises(DBAPIError), db.engine.begin() as connection:
                    connection.execute(text(statement))
    for table in MUTABLE_TABLES:
        with db.engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name=:name"
                    ),
                    {"name": f"aryn_{table}_delete"},
                ).scalar()
                == 1
            )
    # The fixture uses create_all; stamp it to its actual compatible revision.
    from alembic.config import Config
    from alembic import command

    config = Config("alembic.ini")
    with db.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.stamp(config, "019_intelligence_recovery")
    with pytest.raises(RuntimeError, match="intelligence history"):
        migrate_to(db.engine, "018_workflow_execution", downgrade=True)
