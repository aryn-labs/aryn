"""Authenticated workflow routes; each operation revalidates Core scope."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Query, Request
from fastapi.responses import JSONResponse, Response

from database.schema import (
    WorkflowDefinitionModel,
    WorkflowVersionModel,
    WorkflowRunModel,
    WorkflowArtifactModel,
    WorkflowDeliverableModel,
)
from modules.core.workflows.executor import WorkflowExecutor, PREVIEW_CSP
from modules.core.workflows.graph import GraphRejected
from packages.contracts.workflow import SaveWorkflow, Revision, StartWorkflow, Review
from packages.contracts.agent_builder import StopInput


def register_workflows(app, coordinator, context, require_runtime, model_catalog):
    executor = WorkflowExecutor(coordinator)
    executor.recover()
    app.state.workflows = executor
    tasks = {}

    async def execute_background(ctx, identifier):
        try:
            await executor.execute(ctx, identifier)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).error("workflow_background_execution_failed")
        finally:
            tasks.pop(identifier, None)

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            try:
                yield
            finally:
                active = list(tasks.values())
                for task in active:
                    task.cancel()
                await asyncio.gather(*active, return_exceptions=True)

    app.router.lifespan_context = lifespan
    prefix = "/api/projects/{project_id}"

    @app.exception_handler(GraphRejected)
    async def graph_rejected(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "message": "Graph ditolak oleh validator Core.",
                "error_code": "workflow_graph_rejected",
                "issues": exc.issues,
            },
        )

    def queries(request, allowed):
        if any(
            k not in allowed or len(request.query_params.getlist(k)) != 1
            for k in request.query_params
        ):
            from fastapi import HTTPException

            raise HTTPException(422, "Unknown or duplicate query.")

    @app.get(prefix + "/workflow-targets")
    def targets(project_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        return executor.targets(context(project_id), after, limit)

    @app.get(prefix + "/workflow-targets/{assignment_id}")
    def target(project_id: str, assignment_id: str):
        return executor.targets(context(project_id), assignment_id=assignment_id)

    @app.get(prefix + "/workflows")
    def definitions(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
        q: str = Query("", max_length=120),
    ):
        queries(request, {"after", "limit", "q"})
        return executor.inventory(
            context(project_id), WorkflowDefinitionModel, after, limit, q=q
        )

    @app.post(prefix + "/workflows", status_code=201)
    def create(project_id: str, body: SaveWorkflow):
        return executor.draft(context(project_id, "version:create"), body)

    @app.get(prefix + "/workflows/{workflow_id}")
    def definition(project_id: str, workflow_id: str):
        return executor.read(context(project_id), WorkflowDefinitionModel, workflow_id)

    @app.post(prefix + "/workflows/{workflow_id}")
    def save(project_id: str, workflow_id: str, body: SaveWorkflow):
        return executor.draft(context(project_id, "version:create"), body, workflow_id)

    @app.post(prefix + "/workflows/{workflow_id}/validate")
    def validate(project_id: str, workflow_id: str, body: StopInput):
        return executor.validate(context(project_id, "version:create"), workflow_id)

    @app.post(prefix + "/workflows/{workflow_id}/versions", status_code=201)
    def freeze(project_id: str, workflow_id: str, body: Revision):
        return executor.freeze(
            context(project_id, "version:publish"), workflow_id, body
        )

    @app.get(prefix + "/workflows/{workflow_id}/versions")
    def versions(
        project_id: str,
        workflow_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        return executor.inventory(
            context(project_id), WorkflowVersionModel, after, limit, workflow_id
        )

    @app.get(prefix + "/workflow-versions/{id}")
    def version(project_id: str, id: str):
        return executor.read(context(project_id), WorkflowVersionModel, id)

    @app.post(prefix + "/workflows/{workflow_id}/runs")
    async def start(project_id: str, workflow_id: str, body: StartWorkflow, request: Request):
        context(project_id, "run:create")
        await require_runtime()
        from packages.contracts.runtime import GatewayUnavailableError
        if not (await model_catalog()).discovery_valid:
            raise GatewayUnavailableError()
        ctx = context(project_id, "run:create")
        deferred = request.headers.get("Prefer") == "respond-async"
        result = await executor.start(ctx, workflow_id, body, defer=deferred)
        if deferred:
            if result["status"] == "running" and result["id"] not in tasks:
                tasks[result["id"]] = asyncio.create_task(execute_background(ctx, result["id"]))
            return JSONResponse(status_code=202, content=result, headers={"Preference-Applied": "respond-async"})
        return result

    @app.get(prefix + "/workflows/{workflow_id}/runs")
    def runs(
        project_id: str,
        workflow_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        return executor.inventory(
            context(project_id), WorkflowRunModel, after, limit, workflow_id
        )

    @app.get(prefix + "/workflow-runs/{id}")
    def run(project_id: str, id: str):
        return executor.read(context(project_id), WorkflowRunModel, id)

    @app.post(prefix + "/workflow-runs/{id}/stop")
    async def stop(project_id: str, id: str, body: StopInput):
        return await executor.cancel(context(project_id, "run:cancel"), id)

    @app.post(prefix + "/workflow-runs/{id}/review")
    def review(project_id: str, id: str, body: Review):
        return executor.review(context(project_id, "version:approve"), id, body)

    @app.get(prefix + "/workflow-runs/{id}/review")
    def review_receipt(project_id: str, id: str):
        return executor.decision(context(project_id), id)

    @app.get(prefix + "/outputs")
    def outputs(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        return executor.inventory(
            context(project_id), WorkflowArtifactModel, after, limit
        )

    @app.get(prefix + "/deliverables")
    def deliverables(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        return executor.inventory(
            context(project_id), WorkflowDeliverableModel, after, limit
        )

    @app.get(prefix + "/review-queue")
    def review_queue(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        return executor.inventory(
            context(project_id), WorkflowRunModel, after, limit, waiting=True
        )

    @app.get(prefix + "/outputs/{id}")
    def output(project_id: str, id: str):
        return executor.read(context(project_id), WorkflowArtifactModel, id)

    @app.get(prefix + "/deliverables/{id}")
    def deliverable(project_id: str, id: str):
        return executor.read(context(project_id), WorkflowDeliverableModel, id)

    @app.get(prefix + "/outputs/{id}/download")
    def download(project_id: str, id: str):
        artifact, blob = executor.download(context(project_id), id)
        extension = "html" if artifact.mime == "text/html" else "json"
        return Response(
            blob,
            media_type=artifact.mime,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.id}.{extension}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": PREVIEW_CSP,
                "Cache-Control": "no-store",
            },
        )

    @app.get(prefix + "/outputs/{id}/preview")
    def preview(project_id: str, id: str):
        artifact, blob = executor.download(context(project_id), id)
        return Response(
            blob,
            media_type=artifact.mime,
            headers={
                "Content-Security-Policy": PREVIEW_CSP,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )
