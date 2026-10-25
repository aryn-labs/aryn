"""Immutable suite review, scoped execution and unchanged promotion gates."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.integration.test_studio_api import studio as studio, PREFIX, draft


def declaration(**changes):
    return {"family_key": "operational_checks", "evaluation_version": "1.0.0",
        "name": "Operational observations", "description": "Literal observations with mandatory Core integrity checks.",
        "scenarios": [{"scenario_id": "liquidity_observation", "name": "Literal observation",
            "prompt": "Explain liquidity and solvency using their time horizons.", "expected_text": "Liquidity"}], **changes}


def author(client, body=None):
    response = client.post(PREFIX + "/bench/suite-versions", json=body or declaration())
    assert response.status_code == 201, response.text
    return response.json()


def review(client, suite):
    response = client.post(PREFIX + f"/bench/suite-versions/{suite['id']}/review", json={
        "expected_digest": suite["digest"], "reason": "Human review of every scenario and mandatory security grader."})
    assert response.status_code == 200, response.text
    return response.json()


def version_body(suite, number="2.0.0"):
    return {"version_number": number, "system_prompt": "Follow the reviewed operational evaluation and preserve all Core boundaries.",
        "model": "test/model-a", "evaluation_reference": {"suite_id": suite["id"],
            "evaluation_version": suite["evaluation_version"], "required_scenarios": suite["definition"]["scenario_ids"]}}


def test_authored_suite_requires_exact_review_and_runs_existing_engine(studio):
    client, db, runtime, app = studio
    bp, _ = draft(client)
    suite = author(client)
    selected = {item["suite_id"] for item in client.get(PREFIX + "/bench/suites").json()["items"]}
    assert suite["id"] not in selected
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json=version_body(suite))
    assert response.status_code in {403, 409}, response.text
    receipt = review(client, suite)
    assert receipt["target_type"] == "bench_suite" and receipt["payload_hash"] == suite["digest"]
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json=version_body(suite))
    assert response.status_code == 201, response.text
    version = response.json()
    result = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert result.status_code == 200, result.text
    assert result.json()["passed"] and result.json()["suite_hash"] == suite["definition"]["suite_hash"]
    exported = client.get(PREFIX + f"/bench/evaluations/{result.json()['evaluation_id']}/regression/download")
    assert exported.status_code == 200 and exported.json()["attestation"]
    assert exported.headers["cache-control"] == "no-store"


def test_deliberate_regression_stays_rejected_and_failure_requires_human_candidate_review(studio):
    client, db, runtime, app = studio
    bp, _ = draft(client)
    body = declaration()
    body["scenarios"][0]["expected_text"] = "INTENTIONALLY_ABSENT_OBSERVATION"
    suite = author(client, body)
    review(client, suite)
    version = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json=version_body(suite)).json()
    result = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert result.status_code == 200 and not result.json()["passed"], result.text
    assert client.post(PREFIX + f"/versions/{version['id']}/approve", json={
        "payload_hash": version["payload_hash"], "comments": "A failing suite must never authorize publication."}).status_code == 409
    candidate = client.post(PREFIX + "/bench/scenario-candidates", json={"source_kind": "evaluation",
        "source_id": result.json()["evaluation_id"], "scenario": declaration()["scenarios"][0],
        "reason": "Review the failed literal observation before proposing a new suite."})
    assert candidate.status_code == 201, candidate.text
    value = candidate.json()
    next_body = declaration(family_key="reviewed_failure", candidate_id=value["id"])
    assert client.post(PREFIX + "/bench/suite-versions", json=next_body).status_code in {403, 409}
    reviewed = client.post(PREFIX + f"/bench/scenario-candidates/{value['id']}/review", json={
        "expected_digest": value["digest"], "reason": "Explicit human review; this does not accept a quality baseline."})
    assert reviewed.status_code == 200, reviewed.text
    created = author(client, next_body)
    assert created["candidate_id"] == value["id"]
    assert not client.get(PREFIX + "/bench/suite-versions").json()["items"][0]["reviewed"]


def test_suite_immutability_scope_and_current_approver_membership(studio):
    client, db, runtime, app = studio
    suite = author(client)
    review(client, suite)
    assert client.post(PREFIX + "/bench/suite-versions", json=declaration()).status_code == 409
    assert client.post("/api/projects/another_project/bench/suite-versions/" + suite["id"] + "/review", json={
        "expected_digest": suite["digest"], "reason": "Cross project authority must be denied."}).status_code in {403, 404}
    with db.session(write=True) as session:
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE bench_suite_versions SET details_json='{}' WHERE id=:id"), {"id": suite["id"]})
    from services.api.studio import DEV_ACTOR, DEV_PROJECT
    from database.repositories.organization_repo import OrganizationRepository
    with db.session(write=True) as session:
        session.execute(text("UPDATE memberships SET role='viewer' WHERE user_id=:actor"), {"actor": DEV_ACTOR})
        OrganizationRepository(session).add_project_member(DEV_PROJECT, DEV_ACTOR, "viewer")
    ids = {item["suite_id"] for item in client.get(PREFIX + "/bench/suites").json()["items"]}
    assert suite["id"] not in ids


@pytest.mark.parametrize("mutation", ["code", "regex", "remove_security", "host_tools"])
def test_authoring_rejects_executable_or_unbounded_configuration(studio, mutation):
    client, *_ = studio
    body = declaration()
    scenario = body["scenarios"][0]
    if mutation == "code":
        scenario["grader_code"] = "import os"
    elif mutation == "regex":
        scenario["expected_pattern"] = "(a+)+$"
    elif mutation == "remove_security":
        scenario["graders"] = []
    else:
        scenario.update(isolation="isolated_worker", tools=["host_shell"])
    assert client.post(PREFIX + "/bench/suite-versions", json=body).status_code == 422
