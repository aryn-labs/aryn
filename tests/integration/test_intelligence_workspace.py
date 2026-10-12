"""Real Core read projections: identity, bounded history and fail-closed UI authority."""
import json
import pytest
from sqlalchemy import text
from tests.integration.test_studio_api import studio as studio, draft, PREFIX
from services.api.studio import DEV_ACTOR, DEV_PROJECT
from database.repositories.organization_repo import OrganizationRepository
from tests.integration.test_intelligence_recovery import demo_incident, investigated


def evaluated(client, version):
    response = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert response.status_code == 200, response.text
    return response.json()["evaluation_id"]


def test_bench_catalog_exact_identity_and_server_suite(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    identifier = evaluated(client, version)
    listing = client.get(PREFIX + "/bench/evaluations", params={"blueprint_id": bp["id"], "version_id": version["id"], "limit": 1}).json()
    assert [item["id"] for item in listing["items"]] == [identifier]
    item = client.get(PREFIX + "/bench/evaluations/" + identifier).json()
    assert item["verified"] and item["passed"] and item["promotion_eligible"]
    assert item["version_id"] == version["id"] and len(item["scenarios"]) == 4
    assert item["scenarios"][0]["grader_results"]
    assert item["scenarios"][0]["execution"]["cost_usd"] is None
    assert item["scenarios"][0]["execution"]["trace_available"] is False
    assert "attestation" not in json.dumps(item)
    suites = client.get(PREFIX + "/bench/suites").json()["items"]
    assert suites[0]["suite_id"] == item["suite_id"] and len(suites[0]["scenarios"]) == 4
    assert client.get(PREFIX + "/bench/evaluations?suite_id=" + item["suite_id"]).json()["items"][0]["id"] == identifier
    assert client.get(PREFIX + "/bench/evaluations?suite_id=" + item["suite_id"].replace("-", "_")).json()["items"] == []


def test_corrupted_historical_pass_never_becomes_verified_or_promotable(studio):
    client, db, runtime, app = studio
    _, version = draft(client)
    identifier = evaluated(client, version)
    with db.session(write=True) as session:
        session.execute(text("UPDATE bench_evaluations SET provenance_json='{}' WHERE id=:id"), {"id": identifier})
    item = client.get(PREFIX + "/bench/evaluations/" + identifier).json()
    assert item["passed"] and item["passed_scenarios"] == 4
    assert not item["verified"] and not item["promotion_eligible"]
    assert client.get(PREFIX + "/bench/evaluations").json()["items"][0]["verified"] is False


def test_real_failure_and_baseline_cas_visible_through_projection(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    first = evaluated(client, version)
    accepted = client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json={"evaluation_id": first, "reason": "Explicit isolated human acceptance"})
    assert accepted.status_code == 200
    body = {"evaluation_id": first, "expected_baseline_id": None, "reason": "Stale CAS must fail"}
    assert client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json=body).status_code == 409
    runtime.fail = True
    identifier = evaluated(client, version)
    item = client.get(PREFIX + "/bench/evaluations/" + identifier).json()
    assert not item["passed"] and item["verified"] and not item["promotion_eligible"]
    assert item["regression"]["promotion_blocked"]
    assert item["baseline"]["baseline_id"] == accepted.json()["baseline_id"]


def test_source_catalog_and_bundle_links_are_authorized_and_bounded(studio):
    client, db, runtime, app = studio
    _, _, incident = demo_incident(client)
    incident = investigated(client, incident)
    source_page = client.get(PREFIX + "/brief/sources?limit=1").json()
    assert source_page["items"][0]["integrity"] == "VERIFIED"
    assert source_page["items"][0]["freshness"] == "fresh"
    assert source_page["next"]
    links = client.get(PREFIX + f"/brief/{incident['bundle_id']}/links").json()
    assert any(link["reference_id"] == incident["id"] for link in links["items"])
    assert client.get(PREFIX + f"/brief/{incident['bundle_id']}/links?limit=101").status_code == 422


@pytest.mark.parametrize("path", ["/bench/evaluations?limit=101", "/bench/evaluations?status=passed&status=failed", "/bench/evaluations?unexpected=true", "/bench/evaluations?suite_id=invalid%22value"])
def test_projection_query_validation(studio, path):
    client, *_ = studio
    assert client.get(PREFIX + path).status_code == 422


def test_projection_cross_project_revoked_membership_and_viewer_permissions(studio):
    client, db, runtime, app = studio
    _, version = draft(client)
    identifier = evaluated(client, version)
    assert client.get("/api/projects/not-authorized/bench/evaluations/" + identifier).status_code in {403,404}
    before = len(runtime.requests)
    with db.session(write=True) as session:
        session.execute(text("UPDATE memberships SET role='viewer' WHERE user_id=:actor"), {"actor": DEV_ACTOR})
        OrganizationRepository(session).add_project_member(DEV_PROJECT, DEV_ACTOR, "viewer")
    permission = client.get(PREFIX + "/intelligence/context").json()["permissions"]
    assert not permission["version:approve"] and not permission["bench:accept_baseline"]
    assert len(runtime.requests) == before
    with db.session(write=True) as session:
        session.execute(text("DELETE FROM memberships WHERE user_id=:actor"), {"actor": DEV_ACTOR})
    assert client.get(PREFIX + "/bench/evaluations").status_code == 403
