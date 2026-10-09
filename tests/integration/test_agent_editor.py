import copy

import pytest
from sqlalchemy import text

from database.schema import AgentVersionModel, AuditEventModel
from database.repositories.organization_repo import OrganizationRepository
from services.api.studio import DEV_ORG, DEV_ACTOR, DEV_PROJECT
from packages.contracts.agent import AgentVersion
from packages.contracts.agent_builder import AgentDraft
from tests.integration.test_studio_api import PREFIX, draft, promoted, studio as studio


def definition(version):
    return AgentDraft(
        version_number="1.1.0", system_prompt=version["system_prompt"],
        model=version["model"], temperature=version["temperature"], max_tokens=version["max_tokens"],
        role="researcher", objective="Evidence grounded research", owner="team-research",
        model_policy={"primary_model": version["model"], "temperature": version["temperature"],
                      "max_tokens": version["max_tokens"], "provider": "9router", "allowed_models": [version["model"]],
                      "stop_sequences": ["END"]},
        output_contract={"format": "text", "required_sections": ["Evidence"], "description": "Research summary", "strict": True},
        constraints={"disallowed_actions": ["personal advice"], "operational_rules": ["cite evidence"],
                     "require_evidence_citation": True, "max_execution_time_seconds": 90},
        budget_policy={"max_tokens_per_run": 512, "max_turns": 3, "max_cost_usd": 0.1, "timeout_seconds": 90},
    ).model_dump(mode="json")


def test_working_copy_round_trip_candidate_and_layout_independence(studio):
    client, db, _, _ = studio
    bp, version = draft(client)
    base = PREFIX + f"/blueprints/{bp['id']}"
    value = definition(version)
    assert client.get(base + "/working-copy").json()["generation"] == 0
    saved = client.post(base + "/working-copy", json={"expected_generation": 0, "definition": value, "source_version_id": version["id"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["definition"] == value
    assert client.get(base + "/working-copy").json()["definition"] == value
    layout = client.post(base + "/editor-layout", json={"expected_generation": 0, "positions": [{"id": "model", "x": 300, "y": 20}], "viewport": {"x": 10, "y": 0, "zoom": 0.75}})
    assert layout.status_code == 200, layout.text
    assert client.get(base + "/editor-layout").json() == layout.json()
    with db.session() as session:
        assert session.query(AgentVersionModel).count() == 1
        assert session.get(AgentVersionModel, version["id"]).payload_hash == version["payload_hash"]
    candidate = client.post(base + "/working-copy/versions", json={"expected_generation": 1})
    assert candidate.status_code == 201, candidate.text
    with db.session() as session:
        stored = AgentVersion.from_stored(session.get(AgentVersionModel, candidate.json()["id"]))
        stored.verify_integrity(require_canonical=True)
        for field, expected in value.items():
            actual = getattr(stored, field)
            if hasattr(actual, "model_dump"):
                actual = actual.model_dump(mode="json")
            assert actual == expected, field
    projection = client.get(PREFIX + "/lifecycle", params={"version_id": candidate.json()["id"]})
    assert projection.status_code == 200, projection.text
    assert projection.json()["versions"][0]["configuration_loaded"]
    assert any(event["event_type"] == "factory.version.created" and event["authenticated"] for event in projection.json()["audit"])


def test_stale_generation_discard_tombstone_and_immutable_publication(studio):
    client, db, _, _ = studio
    bp, version = draft(client)
    promoted(client, bp, version)
    base = PREFIX + f"/blueprints/{bp['id']}"
    payload = {"expected_generation": 0, "definition": definition(version)}
    assert client.post(base + "/working-copy", json=payload).status_code == 200
    assert client.post(base + "/working-copy", json=payload).status_code == 409
    assert client.post(base + "/working-copy/versions", json={"expected_generation": 2}).status_code == 409
    assert client.post(base + "/working-copy/discard", json={"expected_generation": 1}).json()["generation"] == 2
    assert client.post(base + "/working-copy", json=payload).status_code == 409
    assert client.post(base + "/working-copy/versions", json={"expected_generation": 2}).status_code == 409
    with db.session() as session:
        stored = session.get(AgentVersionModel, version["id"])
        assert stored.status == "published" and stored.payload_hash == version["payload_hash"]


@pytest.mark.parametrize("path,value", [
    (("tool_grants",), ["browser"]), (("tool_policy", "network_access"), True),
    (("tool_policy", "forbidden_tools"), []), (("model_policy", "allow_fallback"), True),
    (("model_policy", "temperature"), 1.5), (("model_policy", "forged"), "authority"),
    (("budget_policy", "max_turns"), 1000), (("evaluation_reference", "suite_id"), "unknown"),
    (("system_prompt",), "short"), (("owner",), "x" * 65),
])
def test_editor_rejects_invalid_and_expanded_authority(studio, path, value):
    client, _, _, _ = studio
    bp, version = draft(client)
    candidate = copy.deepcopy(definition(version))
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/working-copy", json={"expected_generation": 0, "definition": candidate})
    assert response.status_code == 422, response.text


def test_editor_scope_not_found_and_layout_only_accepts_metadata(studio):
    client, _, _, _ = studio
    bp, _ = draft(client)
    base = PREFIX + f"/blueprints/{bp['id']}"
    assert client.get(base.replace("/projects/", "/projects/foreign-") + "/working-copy").status_code in {403, 404}
    assert client.get(PREFIX + "/blueprints/missing/working-copy").status_code == 404
    assert client.post(base + "/editor-layout", json={"expected_generation": 0, "positions": [], "prompt": "private"}).status_code == 422
    assert client.post(base + "/editor-layout", json={"expected_generation": 0, "positions": [{"id": "model", "x": 1, "y": 2}, {"id": "model", "x": 2, "y": 3}]}).status_code == 422
    assert client.get(PREFIX + "/lifecycle?limit=51").status_code == 422
    assert client.get(PREFIX + "/lifecycle?actor_id=forged").status_code == 422


def test_viewer_editor_read_only_and_membership_revocation(studio):
    client, db, _, _ = studio
    bp, version = draft(client)
    base = PREFIX + f"/blueprints/{bp['id']}"
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.get_member(DEV_ORG, DEV_ACTOR).role = "viewer"
        repo.add_project_member(DEV_PROJECT, DEV_ACTOR, "viewer")
    assert client.get(base + "/working-copy").status_code == 200
    assert client.get(base + "/editor-layout").status_code == 200
    assert client.post(base + "/working-copy", json={"expected_generation": 0, "definition": definition(version)}).status_code == 403
    assert client.post(base + "/editor-layout", json={"expected_generation": 0, "positions": []}).status_code == 403
    assert client.post(base + "/working-copy/versions", json={"expected_generation": 1}).status_code == 403
    assert client.get(PREFIX + "/lifecycle").json()["permissions"]["version:create"] is False
    with db.session(write=True) as session:
        OrganizationRepository(session).get_member(DEV_ORG, DEV_ACTOR).status = "inactive"
    assert client.get(base + "/working-copy").status_code == 403
    assert client.get(PREFIX + "/lifecycle").status_code == 403


def test_bounded_reads_capture_history_and_scope_cursor(studio):
    client, _, _, _ = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    response = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "Jelaskan likuiditas.", "idempotency_key": "editor-history-request", "allow_remote_model": True})
    assert response.status_code == 200, response.text
    run = response.json()
    other, other_version = draft(client, "other-agent")
    for index in range(3):
        response = client.post(PREFIX + f"/blueprints/{other['id']}/versions", json={"version_number": f"1.0.{index + 1}", "system_prompt": other_version["system_prompt"], "model": other_version["model"]})
        assert response.status_code == 201
    page = client.get(PREFIX + "/resources/versions", params={"blueprint_id": other["id"], "limit": 1}).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    assert client.get(PREFIX + "/resources/versions", params={"blueprint_id": bp["id"], "limit": 1, "cursor": page["next_cursor"]}).status_code == 422
    captured = client.get(PREFIX + "/lifecycle", params={"run_id": run["run_id"], "version_id": other_version["id"], "limit": 1}).json()
    assert captured["runs"][0]["execution_claim_verified"]
    assert captured["versions"][0]["id"] == version["id"] and captured["versions"][0]["configuration_loaded"]
    assert captured["blueprints"][0]["id"] == bp["id"]
    assert len(client.get(PREFIX + "/lifecycle").json()["runs"]) == 0
    approvals = client.get(PREFIX + "/resources/approvals").json()["items"]
    assert approvals[0]["verified"] and approvals[0]["references"]["payload_hash"] == version["payload_hash"]
    stop = client.post(PREFIX + f"/runs/{run['run_id']}/stop", json={})
    assert stop.status_code == 200, stop.text
    assert stop.json()["cancellation_confirmed"] is False
    assert stop.json()["result"]["status"] == "completed"
    assert client.post(PREFIX + f"/runs/{run['run_id']}/stop", json={"cancellation_confirmed": True}).status_code == 422
    assert client.post(PREFIX + "/runs/missing/stop", json={}).status_code == 404


@pytest.mark.parametrize("operation", ["save", "candidate"])
def test_editor_audit_failure_rolls_back_definition_and_candidate(studio, monkeypatch, operation):
    client, db, _, app = studio
    bp, version = draft(client)
    base = PREFIX + f"/blueprints/{bp['id']}"
    payload = {"expected_generation": 0, "definition": definition(version)}
    if operation == "candidate":
        assert client.post(base + "/working-copy", json=payload).status_code == 200
    original = client.get(base + "/working-copy").json()
    with db.session() as session:
        audit_count = session.query(AuditEventModel).count()
    def fail_audit(*args, **kwargs):
        raise RuntimeError("Injected disposable audit failure")
    monkeypatch.setattr(app.state.factory.audit_logger, "record", fail_audit)
    response = client.post(base + ("/working-copy" if operation == "save" else "/working-copy/versions"),
        json=payload if operation == "save" else {"expected_generation": 1})
    assert response.status_code == 502, response.text
    assert "Injected disposable audit failure" not in response.text
    assert client.get(base + "/working-copy").json() == original
    with db.session() as session:
        assert session.query(AgentVersionModel).count() == 1
        assert session.query(AuditEventModel).count() == audit_count


def test_field_errors_do_not_echo_untrusted_keys_or_values(studio):
    client, _, _, _ = studio
    bp, version = draft(client)
    value = definition(version)
    value["budget_policy"]["max_turns"] = 1000
    value["untrusted-private-field"] = "untrusted-private-value"
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/working-copy", json={"expected_generation": 0, "definition": value})
    assert response.status_code == 422
    assert "definition.budget_policy.max_turns" in {error["field"] for error in response.json()["field_errors"]}
    assert "untrusted-private-field" not in response.text and "untrusted-private-value" not in response.text


def test_active_configuration_survives_bounded_recent_candidate_history(studio):
    client, _, _, _ = studio
    bp, version = draft(client)
    promoted(client, bp, version)
    for index in range(26):
        response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json={"version_number": f"1.1.{index}",
            "system_prompt": version["system_prompt"], "model": version["model"]})
        assert response.status_code == 201, response.text
    response = client.get(PREFIX + "/lifecycle", params={"blueprint_id": bp["id"]})
    assert response.status_code == 200, response.text
    records = response.json()["versions"]
    assert len(records) == 25
    active = next(record for record in records if record["id"] == version["id"])
    assert active["configuration_loaded"] and active["payload_hash"] == version["payload_hash"]
    assert active["registry"]["rollback_eligible"] and active["registry"]["publication_id"]


def test_assignment_page_withholds_verified_action_when_activation_pointer_is_tampered(studio):
    client, db, _, _ = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    resource = PREFIX + "/resources/assignments/" + assignment["id"]
    initial = client.get(resource).json()
    assert initial["verified"] and initial["references"]["activation_verified"]
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE agent_assignments SET current_transition_id=NULL WHERE id=:id"), {"id": assignment["id"]})
    invalid = client.get(resource).json()
    assert invalid["references"]["registry"]["rollback_eligible"]
    assert invalid["verified"] is False and invalid["references"]["activation_verified"] is False
    assert invalid["verification_reason"] == "activation_history_unverified"
