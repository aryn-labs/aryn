"""Real scoped HTTP workspace reads and transactional division contracts."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from database.repositories.organization_repo import OrganizationRepository
from database.schema import DivisionModel, RunStateModel
from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT
from tests.integration.test_studio_api import studio as studio, draft, promoted, PREFIX, ORIGIN


def other_project(db, app, *, foreign=False):
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        org = "other-org" if foreign else DEV_ORG
        if foreign:
            repo.create_organization(org, "Other", "other")
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, org, "other-project")
        repo.create_project(ctx, "other-project", "Other project", "other-project")
    return "/api/projects/other-project"


def test_lightweight_context_summary_and_legacy_compatibility(studio):
    client, _, runtime, _ = studio
    assert client.get("/api/workspace/context").json()["models"] == []
    summary = client.get(PREFIX + "/summary")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["organization_id"] == DEV_ORG and data["project_id"] == DEV_PROJECT
    assert data["metrics"]["blueprints"]["value"] == 0
    assert data["usage"]["cost_usd"] is None and data["usage"]["entitlement"] == "unknown"
    assert data["refreshed_at"] and not runtime.requests
    bp, _ = draft(client)
    assert client.get(PREFIX + "/summary").json()["metrics"]["blueprints"]["value"] == 1
    assert client.get(PREFIX + "/snapshot").json()["blueprints"][0]["id"] == bp["id"]


def test_division_create_edit_conflict_audit_and_persistence(studio):
    client, db, _, app = studio
    body = {"name": "Research", "slug": "research", "description": "Scoped work"}
    response = client.post(PREFIX + "/divisions", json=body)
    assert response.status_code == 201, response.text
    division = response.json()
    assert division["generation"] == 1
    identifier = division["id"]
    detail = client.get(PREFIX + f"/resources/divisions/{identifier}").json()
    assert detail["references"]["assignment_count"] == 0
    payload = {**body, "name": "Evidence", "expected_generation": 1}
    assert client.post(PREFIX + f"/divisions/{identifier}", json=payload).json()["generation"] == 2
    assert client.post(PREFIX + f"/divisions/{identifier}", json=payload).status_code == 409
    assert client.post(PREFIX + "/divisions", json=body).status_code == 409
    with db.session() as session:
        assert session.get(DivisionModel, identifier).name == "Evidence"
    audit = client.get(PREFIX + "/resources/audits").json()["items"]
    assert len(audit) == 2 and all(item["verified"] for item in audit)
    assert "description" not in json.dumps(audit[0]["references"])
    target = other_project(db, app)
    assert client.get(target + f"/resources/divisions/{identifier}").status_code == 404
    assert client.post(target + f"/divisions/{identifier}", json=payload).status_code == 404
    assert client.get(target + "/summary").json()["metrics"]["divisions"]["value"] == 0


def test_division_concurrent_edit_has_one_winner(studio):
    client, _, _, _ = studio
    body = {"name": "Research", "slug": "research"}
    identifier = client.post(PREFIX + "/divisions", json=body).json()["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(PREFIX + f"/divisions/{identifier}",
            json={**body, "expected_generation": 1}).status_code, range(2)))
    assert sorted(results) == [200, 409]


@pytest.mark.parametrize("body", [
    {"name": "x", "slug": "okay"}, {"name": "Valid", "slug": "../escape"},
    {"name": "Valid", "slug": "valid", "organization_id": "other"},
    {"name": "Valid", "slug": "valid", "actor_id": "root", "role": "admin"},
])
def test_division_input_rejects_forgery_and_invalid_fields(studio, body):
    assert studio[0].post(PREFIX + "/divisions", json=body).status_code == 422


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_division_effective_rbac_is_core_owned(studio, role):
    client, db, _, app = studio
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        member = repo.get_member(DEV_ORG, DEV_ACTOR)
        member.role = role
        repo.add_project_member(DEV_PROJECT, DEV_ACTOR, role)
    assert client.get(PREFIX + "/summary").json()["permissions"]["division:manage"] is False
    assert client.post(PREFIX + "/divisions", json={"name": "Denied", "slug": "denied"}).status_code == 403
    assert client.get("/api/workspace/context").status_code == 200
    target = other_project(db, app)
    assert client.get(target + "/summary").status_code == 403
    projects = client.get(PREFIX + "/resources/projects").json()["items"]
    assert [item["id"] for item in projects] == [DEV_PROJECT]


@pytest.mark.parametrize("resource", ["summary", "resources/runs", "resources/projects", "resources/divisions"])
def test_workspace_401_403_tenant_and_revocation(studio, resource):
    client, db, _, app = studio
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as anonymous:
        assert anonymous.get(PREFIX + "/" + resource).status_code == 401
    target = other_project(db, app, foreign=True)
    assert client.get(target + "/" + resource).status_code == 403
    with db.session(write=True) as session:
        OrganizationRepository(session).revoke_member(DEV_ORG, DEV_ACTOR)
    assert client.get(PREFIX + "/" + resource).status_code == 403


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "sort=created_at;drop", "status=forged", "organization_id=other", "actor=someone", "limit=1&limit=2", "cursor=forged"])
def test_page_whitelist_and_tamper_rejection(studio, query):
    assert studio[0].get(PREFIX + "/resources/runs?" + query).status_code == 422


def test_stable_pagination_scope_filter_sort_and_tie_breaker(studio):
    client, db, _, app = studio
    when = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    with db.session(write=True) as session:
        session.add_all([RunStateModel(id=f"fixture-{i:03}", organization_id=DEV_ORG, project_id=DEV_PROJECT,
            prompt="private input", output="private output", model="literal%model" if i == 4 else "test/model",
            provider="test", status="failed" if i % 2 else "completed", created_at=when) for i in range(7)])
    path = PREFIX + "/resources/runs?limit=2&sort=oldest&status=failed"
    page = client.get(path).json()
    assert [item["id"] for item in page["items"]] == ["fixture-001", "fixture-003"]
    cursor = page["next_cursor"]
    next_page = client.get(path + "&cursor=" + cursor).json()
    assert [item["id"] for item in next_page["items"]] == ["fixture-005"]
    assert next_page["next_cursor"] is None
    assert "private input" not in json.dumps(page) and "private output" not in json.dumps(page)
    assert not any(item["verified"] for item in page["items"])
    attention = client.get(PREFIX + "/summary").json()["attention"]
    assert attention == [{"code": "failed", "count": 3,
        "description": "Run gagal tersimpan; telusuri error dan evidence", "route": "/runs/fixture-005"}]
    assert client.get(path + "&cursor=" + cursor[:-1] + ("a" if cursor[-1] != "a" else "b")).status_code == 422
    assert client.get(PREFIX + "/resources/runs?limit=2&sort=newest&status=failed&cursor=" + cursor).status_code == 422
    target = other_project(db, app)
    assert client.get(target + "/resources/runs?limit=2&sort=oldest&status=failed&cursor=" + cursor).status_code == 422
    assert len(client.get(PREFIX + "/resources/runs?q=%25").json()["items"]) == 1
    assert client.get(PREFIX + "/resources/runs/missing").status_code == 404


def test_summary_verification_uses_actual_evidence_and_captured_claim(studio):
    client, db, _, _ = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    response = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "Explain evidence safely.",
        "idempotency_key": "workspace-contract-run", "allow_remote_model": True})
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    summary = client.get(PREFIX + "/summary").json()
    assert summary["metrics"]["published"]["value"] == 1 and summary["metrics"]["assigned"]["value"] == 1
    assert summary["latest_runs"][0]["verified"] is True
    assert all(item["verified"] for item in summary["latest_audits"])
    assert client.get(PREFIX + f"/resources/runs/{run_id}").json()["references"]["result"]["agent_version_id"] == version["id"]
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE run_states SET execution_attestation='forged' WHERE id=:id"), {"id": run_id})
    summary = client.get(PREFIX + "/summary").json()
    assert summary["latest_runs"][0]["verified"] is False
    detail = client.get(PREFIX + f"/resources/runs/{run_id}").json()
    assert "result" not in detail["references"]
    assert detail["references"]["total_tokens"] is None
