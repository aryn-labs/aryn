"""Captured Core identity across HTTP preflight, SSE, restart and idempotency."""
import json

import pytest
from sqlalchemy import text

from services.api.studio import create_app
from tests.integration.test_studio_api import studio as studio
from tests.integration.test_studio_api import draft, promoted, PREFIX
from tests.integration.test_agent_registry_api import published_pair


@pytest.mark.parametrize("stream", [False, True])
def test_rollback_during_preflight_json_sse_and_cache_use_captured_identity(studio, stream):
    client, db, runtime, app = studio
    bp, first, second, assignment, intent = published_pair(client)
    original = runtime.require_model_available
    switched = False
    # Use server-provided context instead of browser actor claims.
    from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT
    async def rollback_during_preflight(model):
        nonlocal switched
        await original(model)
        if not switched:
            switched = True
            app.state.factory.rollback_assignment(app.state.binder.create_trusted_context(
                DEV_ACTOR, DEV_ORG, DEV_PROJECT), assignment["id"], intent)
    runtime.require_model_available = rollback_during_preflight
    body = {"assignment_id": assignment["id"], "prompt": "Captured exact version during preflight",
            "idempotency_key": "captured-preflight", "allow_remote_model": True}
    headers = {"Accept": "text/event-stream"} if stream else {}
    response = client.post(PREFIX + "/runs", json=body, headers=headers)
    assert response.status_code == 200, response.text
    def result(response):
        if not stream:
            return response.json()
        events = [part.splitlines() for part in response.text.split("\n\n") if part]
        # Pre-claim events carry intent only; no stale version metadata is published.
        first_event = json.loads(events[0][1].removeprefix("data: "))
        assert "version_id" not in first_event and "model" not in first_event
        return json.loads(next(e[1] for e in events if e[0] == "event: run.completed").removeprefix("data: "))
    captured = result(response)
    assert captured["agent_version_id"] == first["id"]
    assert captured["agent_payload_hash"] == first["payload_hash"]
    assert captured["requested_model"] == captured["actual_model"] == captured["model"]
    assert captured["execution_provenance"]["version_id"] == first["id"]
    assert captured["output_reference"] and captured["usage"]["availability"] == "measured"
    assert runtime.requests[-1].system_instructions == first["system_prompt"]
    cached = result(client.post(PREFIX + "/runs", json=body, headers=headers))
    assert cached == captured
    with db.session() as session:
        payloads = session.execute(text("SELECT redacted_payload_json FROM audit_events WHERE event_type='studio.run.assignment' AND resource_id=:id"), {"id": captured["run_id"]}).scalars().all()
        assert payloads and all(json.loads(p)["version_id"] == first["id"] for p in payloads)


@pytest.mark.parametrize("stream", [False, True])
def test_dependency_secret_is_never_public_or_audit_error(studio, stream, caplog):
    client, db, runtime, _ = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    secret = "sk-synthetic-provider-credential-in-exception"
    async def dependency_error(request, context):
        raise RuntimeError(f"nested provider password={secret}")
    runtime.execute_direct_turn = dependency_error
    response = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"],
        "prompt": "Research with api_key=sk-synthetic-prompt-credential", "idempotency_key": "secret-error-request",
        "allow_remote_model": True}, headers={"Accept": "text/event-stream"} if stream else {})
    assert response.status_code == (200 if stream else 502)
    assert secret not in response.text + caplog.text
    assert "error_code" in response.text
    with db.session() as session:
        payloads = session.execute(text("SELECT redacted_payload_json FROM audit_events")).scalars().all()
        assert secret not in str(payloads) and "sk-synthetic-prompt-credential" not in str(payloads)
        assert session.execute(text("SELECT status FROM run_states WHERE idempotency_key='secret-error-request'")).scalar() == "outcome_unknown"


def test_live_bench_is_not_interrupted_by_second_app_startup(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    execute = runtime.execute_direct_turn
    started_second = False
    async def second_startup(request, context):
        nonlocal started_second
        if not started_second:
            started_second = True
            create_app(db, runtime, testing=True)
            with db.session() as session:
                assert session.execute(text("SELECT status FROM agent_versions WHERE id=:id"), {"id": version["id"]}).scalar() == "evaluating"
                assert session.execute(text("SELECT COUNT(*) FROM audit_events WHERE event_type='bench.evaluation.interrupted'")).scalar() == 0
        return await execute(request, context)
    runtime.execute_direct_turn = second_startup
    response = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert response.status_code == 200 and response.json()["passed"], response.text


@pytest.mark.parametrize("stream", [False, True])
def test_in_progress_cache_preserves_actor_binding_and_claim_authority(studio, monkeypatch, stream):
    from database.repositories.organization_repo import OrganizationRepository
    from database.repositories.run_state_repo import RunStateRepository
    from services.api.studio import DEV_ORG
    client, db, runtime, app = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    core = app.state.coordinator
    def pending(run_id, result, ctx):
        with db.session() as session:
            return core.stored_result(RunStateRepository(session).get_run(ctx, run_id))
    monkeypatch.setattr(core, "_complete_dispatch", pending)
    body = {"assignment_id": assignment["id"], "prompt": "Captured pending input",
        "idempotency_key": "pending-claim-authority", "allow_remote_model": True}
    headers = {"Accept": "text/event-stream"} if stream else {}
    created = client.post(PREFIX + "/runs", json=body)
    assert created.status_code == 200 and created.json()["status"] == "started"
    run_id = created.json()["run_id"]
    count = len(runtime.requests)
    cached = client.post(PREFIX + "/runs", json=body, headers=headers)
    assert cached.status_code == 200 and run_id in cached.text and len(runtime.requests) == count
    with db.session(write=True) as session:
        OrganizationRepository(session).add_member(DEV_ORG, "other-admin", role="admin")
    original = app.state.binder.create_trusted_context
    monkeypatch.setattr(app.state.binder, "create_trusted_context",
        lambda actor, org, project, **kwargs: original("other-admin", org, project, **kwargs))
    assert client.post(PREFIX + "/runs", json=body, headers=headers).status_code == 409
    monkeypatch.setattr(app.state.binder, "create_trusted_context", original)
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE run_states SET execution_claim_json=NULL,execution_attestation=NULL,execution_owner_id=NULL WHERE id=:id"), {"id": run_id})
    assert client.post(PREFIX + "/runs", json=body, headers=headers).status_code == 403
    assert len(runtime.requests) == count
