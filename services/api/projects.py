"""Projects HTTP contracts, with existing Studio and Core security boundaries."""
from fastapi import HTTPException, Query, Request
from packages.contracts.projects import ProjectInput, ProjectUpdate
from modules.core.projects import ProjectService, project_view
from database.repositories.exceptions import EntityNotFoundError
from database.schema import ProjectModel
from modules.core.errors import sanitize
from services.api.project_reads import ProjectReads


def register_projects(app, db, permissions, context, workspace_reads):
    service = ProjectService(db, permissions)
    app.state.projects = service
    reads = ProjectReads(workspace_reads)

    @app.get("/api/projects/{project_id}/project-resources/{collection}")
    def resources(project_id: str, collection: str, request: Request, q: str = Query("", max_length=120),
            format: str = Query("", max_length=80), kind: str = Query("", max_length=30), active_only: bool = False,
            limit: int = Query(25, ge=1, le=100), cursor: str | None = Query(None, max_length=2048)):
        whitelist(request, {"q", "format", "limit", "cursor", "kind", "active_only"})
        return reads.page(context(project_id), collection, limit, cursor, q, format, kind, active_only)

    @app.get("/api/projects/{project_id}/project-resources/detail/{kind}/{identifier}")
    def resource_detail(project_id: str, kind: str, identifier: str):
        return reads.detail(context(project_id), kind, identifier)

    def clean(value):
        return sanitize(value, credentials=getattr(db, "protected_credentials", ()))

    def whitelist(request, allowed):
        if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise HTTPException(422)

    @app.get("/api/projects")
    def projects(request: Request, q: str = Query("", max_length=120), limit: int = Query(25, ge=1, le=100), cursor: str | None = Query(None, max_length=2048)):
        whitelist(request, {"q", "limit", "cursor"})
        ctx = context("")
        page = workspace_reads.page(ctx, "projects", q=q, limit=limit, cursor=cursor)
        with db.session() as session:
            workspace_reads.authorize(session, ctx)
            return clean({**page, "can_create": permissions.evaluate("project:create", ctx, ctx.organization_id, session=session).allowed})

    @app.post("/api/projects", status_code=201)
    def create(body: ProjectInput):
        return clean(service.save(context("", "project:create"), body))

    @app.get("/api/projects/{project_id}")
    def detail(project_id: str):
        ctx = context(project_id)
        with db.session() as session:
            workspace_reads.authorize(session, ctx)
            record = session.query(ProjectModel).filter_by(id=project_id, organization_id=ctx.organization_id).first()
            if record is None:
                raise EntityNotFoundError("Project unavailable.")
            result = {**project_view(record), "can_edit": permissions.evaluate("project:update", ctx,
                ctx.organization_id, ctx.project_id, session=session).allowed}
            workspace_reads.authorize(session, ctx)
            return clean(result)

    @app.patch("/api/projects/{project_id}")
    def edit(project_id: str, body: ProjectUpdate):
        return clean(service.save(context(project_id, "project:update"), body, project_id))
