"""Informational interpretation uses the existing assigned Core run authority."""

from sqlalchemy import text
import pytest
from tests.integration.test_studio_api import studio as studio, PREFIX, draft, promoted
from tests.integration.test_intelligence_recovery import post
from tests.integration.test_brief_local_evidence import bundle


def setup_interpretation(client):
    bp, version = draft(client, "brief-interpretation")
    assignment = promoted(client, bp, version)
    source = post(client, "/brief/documents", {"title": "Sanitized evidence", "text": "approved recovery requires human review"})["source"]
    captured = bundle(client, source)
    request = {"assignment_id": assignment["id"], "allow_remote_model": True,
        "idempotency_key": "explicit-interpretation-request"}
    return captured, request


def test_interpretation_is_scoped_informational_signed_and_idempotent(studio):
    client, db, runtime, app = studio
    captured, request = setup_interpretation(client)
    before = len(runtime.requests)
    result = post(client, f"/brief/{captured['id']}/interpret", request)
    assert result["authority"] == "informational_only" and result["classification"] == "model_interpretation"
    assert result["evidence_status"] == "SUPPORTED" and result["core_run_id"]
    assert len(runtime.requests) == before + 1
    repeated = post(client, f"/brief/{captured['id']}/interpret", request)
    assert repeated == result and len(runtime.requests) == before + 1
    current = client.get(PREFIX + "/brief/" + captured["id"]).json()
    assert current["evaluation"]["status"] == captured["evaluation"]["status"]
    records = client.get(PREFIX + f"/brief/{captured['id']}/interpretations").json()["items"]
    assert records == [result]
    assert client.get("/api/projects/another_project/brief/" + captured["id"] + "/interpretations").status_code in {403, 404}


@pytest.mark.parametrize("change", ["missing_consent", "wrong_assignment", "revoked_assignment", "cross_project"])
def test_interpretation_denial_never_invokes_runtime(studio, change):
    client, db, runtime, app = studio
    captured, request = setup_interpretation(client)
    path = PREFIX + f"/brief/{captured['id']}/interpret"
    if change == "missing_consent":
        request["allow_remote_model"] = False
    elif change == "wrong_assignment":
        request["assignment_id"] = "missing_assignment"
    elif change == "revoked_assignment":
        with db.session(write=True) as session:
            session.execute(text("UPDATE agent_assignments SET status='inactive' WHERE id=:id"), {"id": request["assignment_id"]})
    else:
        path = "/api/projects/another_project/brief/" + captured["id"] + "/interpret"
    before = len(runtime.requests)
    response = client.post(path, json=request)
    assert response.status_code in {403, 404, 409, 422}, response.text
    assert len(runtime.requests) == before
