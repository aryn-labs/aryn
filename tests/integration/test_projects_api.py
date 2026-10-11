"""Real API/Core/database project mutations; runtime doubles are test-only."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from database.repositories.organization_repo import OrganizationRepository
from database.schema import ProjectModel, ProjectMutationModel, AuditEventModel
from modules.core.permissions.engine import PermissionDeniedError
from packages.contracts.projects import ProjectInput
from tests.integration.test_studio_api import studio as studio, PREFIX, ORIGIN, draft, promoted
from services.api.studio import DEV_ORG, DEV_ACTOR
from tests.integration.test_workflow_execution import workflow as workflow
from database.connection import DatabaseManager, create_db_engine, init_db
from services.api.studio import create_app
from tests.studio_runtime import IsolatedTestRuntime
from tests.integration.test_conversations import raw_studio as raw_studio, chat_studio as chat_studio, CHAT, payload, complete


def body(name="Projects validation", **values):
    return {"name": name, "description": "Real Core metadata transaction", "idempotency_key": uuid.uuid4().hex, **values}


def test_create_edit_receipt_audit_refresh_and_duplicates(studio):
    client, db, _, _ = studio
    payload = body()
    created = client.post("/api/projects", json=payload)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["generation"] == 1 and item["organization_id"] == DEV_ORG
    assert client.post("/api/projects", json=payload).json() == item
    assert client.post("/api/projects", json=body()).status_code == 409
    assert client.post("/api/projects", json={**payload, "name": "different"}).status_code == 409
    target = "/api/projects/" + item["id"]
    edit = body("Renamed project", expected_generation=1)
    updated = client.patch(target, json=edit)
    assert updated.status_code == 200, updated.text
    assert updated.json()["generation"] == 2
    assert client.patch(target, json=edit).json() == updated.json()
    assert client.patch(target, json=body("stale", expected_generation=1)).status_code == 409
    assert client.get(target).json()["name"] == "Renamed project"
    page = client.get("/api/projects?q=Renamed").json()
    assert [record["id"] for record in page["items"]] == [item["id"]]
    with db.session() as session:
        assert session.query(ProjectMutationModel).filter_by(project_id=item["id"]).count() == 2
        events = session.query(AuditEventModel).filter_by(project_id=item["id"]).all()
        assert {event.event_type for event in events} == {"core.project.created", "core.project.updated"}
    assert all(event["verified"] for event in client.get(target + "/resources/audits").json()["items"])
    assert client.delete(target).status_code == 405


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_zero_project_creation_is_org_scoped(studio, role):
    _, db, _, app = studio
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.create_organization("empty-org", "Empty", "empty-org")
        repo.add_member("empty-org", "empty-user", role)
    ctx = app.state.binder.create_trusted_context("empty-user", "empty-org", "")
    if role == "admin":
        result = app.state.projects.save(ctx, ProjectInput(**body()))
        assert result["organization_id"] == "empty-org"
    else:
        with pytest.raises(PermissionDeniedError):
            app.state.projects.save(ctx, ProjectInput(**body()))
    with db.session() as session:
        assert session.query(ProjectModel).filter_by(organization_id="empty-org").count() == (1 if role == "admin" else 0)


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_zero_project_http_authorization_and_refresh(tmp_path, role):
    db = DatabaseManager(create_db_engine(f"sqlite:///{tmp_path / 'empty-projects.sqlite3'}"))
    init_db(db.engine)
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.create_organization(DEV_ORG, "Empty organization", "empty-organization")
        repo.add_member(DEV_ORG, DEV_ACTOR, role)
    app = create_app(db, IsolatedTestRuntime(), testing=True)
    try:
        with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 2)) as client:
            session = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
            client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrf"]})
            context = client.get("/api/workspace/context").json()
            assert context["projects"] == []
            listing = client.get("/api/projects").json()
            assert listing["items"] == [] and listing["can_create"] == (role == "admin")
            result = client.post("/api/projects", json=body())
            assert result.status_code == (201 if role == "admin" else 403), result.text
            after = client.get("/api/workspace/context").json()["projects"]
            assert len(after) == (1 if role == "admin" else 0)
            if role == "admin":
                assert after[0]["id"] == result.json()["id"]
    finally:
        db.engine.dispose()


def test_project_catalog_never_exposes_private_chat_output(chat_studio):
    client, db, _, _ = chat_studio
    response = client.post(CHAT, json=payload())
    assert response.status_code == 202, response.text
    conversation = complete(client, response.json()["id"])
    assert conversation["status"] == "completed"
    from database.schema import ConversationTurnModel
    with db.session() as session:
        run_id = session.query(ConversationTurnModel).one().run_id
    for collection in ("work", "results"):
        assert run_id not in {item["id"] for item in client.get(PREFIX + "/project-resources/" + collection).json()["items"]}
    assert client.get(PREFIX + "/project-resources/detail/run/" + run_id).status_code == 404


@pytest.mark.parametrize("values", [{"name": "x"}, {"name": ""}, {"name": "New\nName"}, {"description": "a" * 2001}, {"organization_id": "foreign"}, {"actor_id": "admin"}, {"idempotency_key": "short"}])
def test_project_validated_input(studio, values):
    assert studio[0].post("/api/projects", json=body(**values)).status_code == 422


def test_auth_csrf_origin_revocation_and_project_boundary(studio):
    client, db, _, app = studio
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 2)) as anon:
        assert anon.get("/api/projects").status_code == 401
        assert anon.post("/api/projects", json=body(), headers={"Origin": ORIGIN}).status_code == 401
    assert client.post("/api/projects", json=body(), headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert client.post("/api/projects", json=body(), headers={"Origin": "https://foreign.invalid"}).status_code == 403
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.create_organization("other-org", "Other", "other-org")
        foreign_ctx = app.state.binder.create_trusted_context("other", "other-org", "other-project")
        repo.create_project(foreign_ctx, "other-project", "Private", "private")
    assert client.get("/api/projects/other-project").status_code == 403
    assert client.patch("/api/projects/other-project", json=body(expected_generation=1)).status_code == 403
    with db.session(write=True) as session:
        OrganizationRepository(session).revoke_member(DEV_ORG, DEV_ACTOR)
    assert client.get("/api/projects").status_code == 403
    assert client.post("/api/projects", json=body()).status_code == 403


def test_project_pagination_filters_and_cursor_binding(studio):
    client = studio[0]
    for index in range(4):
        assert client.post("/api/projects", json=body(f"Page {index}")).status_code == 201
    page = client.get("/api/projects?limit=2&q=Page").json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    more = client.get("/api/projects?limit=2&q=Page&cursor=" + page["next_cursor"]).json()
    assert len(more["items"]) == 2 and not more["next_cursor"]
    assert set(item["id"] for item in page["items"]).isdisjoint(item["id"] for item in more["items"])
    assert client.get("/api/projects?q=other&limit=2&cursor=" + page["next_cursor"]).status_code == 422
    for query in ("limit=0", "limit=101", "cursor=forged", "status=active", "q=one&q=two", "organization_id=other"):
        assert client.get("/api/projects?" + query).status_code == 422


def test_concurrent_project_edits_and_immutable_receipts(studio):
    client, db, _, _ = studio
    item = client.post("/api/projects", json=body()).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: client.patch("/api/projects/" + item["id"], json=body(f"Winner {i}", expected_generation=1)).status_code, (1, 2)))
    assert sorted(results) == [200, 409]
    for statement in ("UPDATE project_mutations SET request_hash='forged'", "DELETE FROM project_mutations"):
        with pytest.raises(Exception, match="append-only"):
            with db.engine.begin() as connection:
                connection.execute(text(statement))


def test_project_projections_actual_assignment_evaluation_output_and_scope(studio):
    client, db, _, app = studio
    blueprint, version = draft(client)
    assignment = promoted(client, blueprint, version)
    run = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "Explain governed outputs safely", "idempotency_key": "projects-real-core-output", "allow_remote_model": True})
    assert run.status_code == 200, run.text
    for collection in ("work", "team", "results", "activity"):
        response = client.get(PREFIX + "/project-resources/" + collection)
        assert response.status_code == 200, response.text
        assert response.json()["items"]
    results = client.get(PREFIX + "/project-resources/results").json()
    assert {item["kind"] for item in results["items"]} == {"run", "evaluation"}
    item = next(item for item in results["items"] if item["kind"] == "run")
    detail = client.get(PREFIX + "/project-resources/detail/run/" + item["id"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["preview"]["text"] and detail.json()["verified"]
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "different-project")
    with db.session(write=True) as session:
        OrganizationRepository(session).create_project(ctx, "different-project", "Different", "different")
    assert client.get("/api/projects/different-project/project-resources/detail/run/" + item["id"]).status_code == 404
    assert not client.get("/api/projects/different-project/project-resources/results").json()["items"]
    assert client.get(PREFIX + "/project-resources/results?format=evaluation").json()["items"][0]["kind"] == "evaluation"


def test_governed_workflow_artifacts_and_metadata_only_website(workflow):
    client, _, _, _, definition, version = workflow
    response = client.post(PREFIX + f"/workflows/{definition['id']}/runs", json={"version_id": version["id"], "input": "Create a safe document", "idempotency_key": "project-artifact-preview", "allow_remote_model": True})
    assert response.status_code == 200, response.text
    artifacts = client.get(PREFIX + "/project-resources/results").json()["items"]
    assert {item["format"] for item in artifacts if item["kind"] == "artifact"} == {"brief", "content", "website"}
    for item in artifacts:
        detail = client.get(PREFIX + f"/project-resources/detail/{item['kind']}/{item['id']}")
        assert detail.status_code == 200, detail.text
        if item["format"] == "website":
            assert "preview" not in detail.json()
            assert detail.json()["references"]["digest"]
