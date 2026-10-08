"""Workspace endpoints use real signed offline OIDC/Core sessions."""
from datetime import datetime, timedelta, timezone

from database.repositories.organization_repo import OrganizationRepository
from database.schema import AuthSessionModel
from tests.security.test_deployment_authentication import hosted as hosted, login


def test_hosted_workspace_scope_effective_permissions_and_expiry(hosted):
    client, _, db, *_ = hosted
    assert client.get("/api/workspace/context").status_code == 401
    assert client.get("/api/projects/project/summary").status_code == 401
    login(hosted)
    context = client.get("/api/workspace/context")
    assert context.status_code == 200 and context.json()["mode"] == "hosted"
    assert [project["id"] for project in context.json()["projects"]] == ["project"]
    assert client.get("/api/projects/private/summary").status_code == 403
    assert client.get("/api/projects/foreign-project/resources/divisions").status_code == 403
    summary = client.get("/api/projects/project/summary").json()
    assert summary["permissions"]["division:manage"] is False
    assert client.post("/api/projects/project/divisions", json={"name": "Denied", "slug": "denied"}).status_code == 403
    with db.session(write=True) as session:
        session.query(AuthSessionModel).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    assert client.get("/api/projects/project/summary").status_code == 401
    assert client.get("/api/workspace/context").status_code == 401


def test_hosted_workspace_revokes_membership_at_write_commit(hosted):
    client, app, db, *_ = hosted
    login(hosted)
    with db.session(write=True) as session:
        OrganizationRepository(session).get_member("org", "human").role = "admin"
    ctx = app.state.binder.create_trusted_context("human", "org", "project")
    from packages.contracts.workspace import DivisionInput
    with db.session(write=True) as session:
        OrganizationRepository(session).revoke_member("org", "human")
    from modules.core.permissions.engine import PermissionDeniedError
    import pytest
    with pytest.raises(PermissionDeniedError):
        app.state.workspace_service.save_division(ctx, DivisionInput(name="Revoked", slug="revoked"))
    assert client.get("/api/projects/project/resources/divisions").status_code == 403
