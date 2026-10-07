"""AF-07: server-derived registry and assignment-scoped rollback HTTP authority."""
from tests.integration.test_studio_api import studio as studio
from tests.integration.test_studio_api import draft, promoted, PREFIX


def published_pair(client):
    bp, first = draft(client)
    promoted(client, bp, first)
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json={"version_number": "2.0.0",
        "system_prompt": "Second reviewed agent follows research safety guidelines.", "model": first["model"], "max_tokens": 512})
    assert response.status_code == 201
    second = response.json()
    for route, body in (("bench", {"allow_remote_model": True}), ("approve", {"payload_hash": second["payload_hash"], "comments": "Reviewed second publication."}), ("publish", {})):
        response = client.post(PREFIX + f"/versions/{second['id']}/{route}", json=body)
        assert response.status_code == 200, response.text
    assignment = client.post(PREFIX + "/assignments", json={"blueprint_id": bp["id"], "version_id": second["id"], "role_name": "Candidate operations"})
    assert assignment.status_code == 201
    assignment = assignment.json()
    body = {"target_version_id": first["id"], "expected_current_version_id": second["id"],
        "expected_transition_id": assignment["current_transition_id"], "reason": "Restore reviewed prior agent.", "idempotency_key": "rollback-http-intent"}
    return bp, first, second, assignment, body


def test_registry_rollback_api_freezes_run_identity_and_preserves_baseline(studio):
    client, db, _, _ = studio
    bp, first, second, assignment, body = published_pair(client)
    registry = client.get(PREFIX + f"/blueprints/{bp['id']}/registry")
    assert registry.status_code == 200 and all(v["rollback_eligible"] for v in registry.json())
    before = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "Before rollback request", "allow_remote_model": True, "idempotency_key": "before-http-run-key"})
    assert before.status_code == 200, before.text
    assert before.json()["agent_version_id"] == second["id"]
    prior_snapshot = client.get(PREFIX + "/snapshot").json()
    response = client.post(PREFIX + f"/assignments/{assignment['id']}/rollback", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["from_version_id"] == second["id"] and response.json()["to_version_id"] == first["id"]
    assert client.post(PREFIX + f"/assignments/{assignment['id']}/rollback", json=body).json() == response.json()
    after = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "After rollback request", "allow_remote_model": True, "idempotency_key": "after-http-run-key"})
    assert after.status_code == 200, after.text
    assert after.json()["agent_version_id"] == first["id"]
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert snapshot["accepted_baselines"] == prior_snapshot["accepted_baselines"]
    active = next(a for a in snapshot["assignments"] if a["id"] == assignment["id"])
    assert active["activation_verified"] and len(active["activation_history"]) == 2
    assert all(run["assignment_provenance_verified"] for run in snapshot["runs"])
    assert next(run for run in snapshot["runs"] if run["id"] == before.json()["run_id"])["agent_version_id"] == second["id"]


def test_browser_truth_stale_state_and_unauthorized_rollback_fail_closed(studio):
    client, db, _, _ = studio
    bp, first, second, assignment, body = published_pair(client)
    route = PREFIX + f"/assignments/{assignment['id']}/rollback"
    for field in ("known_good", "verified", "rollback_safe", "approved", "bench_passed"):
        assert client.post(route, json={**body, field: True}).status_code == 422
    assert client.post(route, json={**body, "reason": " "}).status_code == 422
    assert client.post(route, json={**body, "expected_current_version_id": first["id"]}).status_code == 409
    assert client.post(route, json={**body, "expected_transition_id": "stale"}).status_code == 409
    assert client.post(route, json=body).status_code == 200
    assert client.post(route, json={**body, "reason": "Different rollback reason."}).status_code == 409
    from sqlalchemy import text
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE memberships SET role='viewer'"))
    assert client.post(route, json=body).status_code == 403
