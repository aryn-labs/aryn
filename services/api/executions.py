"""Session-bound observation and explicit stop through existing Core."""

from fastapi import Query, Request, HTTPException
from packages.contracts.agent_builder import StopInput
from services.api.execution_reads import ExecutionReads


def register_executions(app, reads, editor, context):
    executions = ExecutionReads(reads, editor)
    app.state.executions = executions
    prefix = "/api/projects/{project_id}/executions"

    @app.get(prefix)
    def catalog(
        project_id: str,
        request: Request,
        q: str = Query("", max_length=160),
        kind: str = Query("", pattern=r"^(|agent|workflow)$"),
        status: str = Query(
            "",
            pattern=r"^(|queued|started|running|stopping|completed|failed|cancelled|outcome_unknown|waiting_review|rejected)$",
        ),
        after: str = Query("", max_length=4096),
        limit: int = Query(25, ge=1, le=100),
        order: str = Query("desc", pattern=r"^(asc|desc)$"),
        since: str = Query("", max_length=40),
        until: str = Query("", max_length=40),
    ):
        allowed = {"q", "kind", "status", "after", "limit", "order", "since", "until"}
        if any(
            k not in allowed or len(request.query_params.getlist(k)) != 1
            for k in request.query_params
        ):
            raise HTTPException(422, "Unknown or duplicate execution query.")
        return executions.catalog(
            context(project_id),
            q=q,
            kind=kind,
            status=status,
            after=after,
            limit=limit,
            order=order,
            since=since,
            until=until,
        )

    @app.get(prefix + "/{kind}/{identifier}")
    def detail(project_id: str, kind: str, identifier: str):
        if kind not in {"agent", "workflow"}:
            raise HTTPException(404)
        return executions.detail(context(project_id), kind, identifier)

    @app.post(prefix + "/{kind}/{identifier}/stop")
    async def stop(project_id: str, kind: str, identifier: str, body: StopInput):
        ctx = context(project_id, "run:cancel")
        executions.detail(ctx, kind, identifier)
        if kind == "workflow":
            await executions.workflows.cancel(ctx, identifier)
        elif kind == "agent":
            await reads.coordinator.cancel_managed_run(identifier, ctx)
        return executions.detail(context(project_id), kind, identifier)
