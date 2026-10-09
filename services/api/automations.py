"""Scoped scheduling routes and the single Core owner's application lifespan."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from fastapi import Query, Request, HTTPException
from database.schema import AutomationOccurrenceModel, AutomationEventModel
from modules.core.automations.service import CoreAutomations
from modules.core.automations.recurrence import preview
from modules.core.capabilities import Capabilities
from modules.core.workflows.ownership import ExecutionOwnershipError
from packages.contracts.automation import (
    AutomationInput,
    AutomationDecision,
    AutomationStateInput,
    ManualOccurrence,
    ReconcileOccurrence,
    PreviewInput,
)


def register_automations(
    app, coordinator, context, require_runtime, *, testing=False, local=True
):
    scheduler = CoreAutomations(coordinator, require_runtime=require_runtime)
    scheduler.recover()
    app.state.automations = scheduler
    capabilities = Capabilities(coordinator)
    prefix = "/api/projects/{project_id}"

    def query_keys(request, allowed):
        if any(
            key not in allowed or len(request.query_params.getlist(key)) != 1
            for key in request.query_params
        ):
            raise HTTPException(422, "Unknown or duplicate schedule query.")

    @app.get(prefix + "/capabilities")
    async def registry(project_id: str, request: Request):
        query_keys(request, set())
        context(project_id)
        ready = False
        try:
            health = await coordinator.runtime_adapter.health()
            caps = await coordinator.runtime_adapter.capabilities()
            ready = (
                health.is_healthy and caps.tools_confined and not caps.enabled_toolsets
            )
        except Exception:
            pass
        return capabilities.read(
            context(project_id), "local" if local else "hosted", ready
        )

    @app.post(prefix + "/automation-preview")
    def schedule_preview(project_id: str, body: PreviewInput):
        context(project_id)
        return {
            "instants": preview(body.schedule, scheduler.clock()),
            "dst_gap": "skip",
            "dst_fold": "first_only",
            "interval_clock": "UTC",
        }

    @app.get(prefix + "/automation-targets")
    def targets(
        project_id: str,
        request: Request,
        kind: str = Query("agent", pattern=r"^(agent|workflow)$"),
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        query_keys(request, {"kind", "after", "limit"})
        return scheduler.targets(
            context(project_id, "version:approve"), kind, after, limit
        )

    @app.get(prefix + "/automations")
    def definitions(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
        q: str = Query("", max_length=160),
        status: str = Query("", pattern=r"^(|enabled|paused)$"),
    ):
        query_keys(request, {"after", "limit", "q", "status"})
        ctx = context(project_id)
        return {
            **scheduler.inventory(ctx, after=after, limit=limit, q=q, status=status),
            "scheduler": scheduler.status(),
        }

    @app.post(prefix + "/automations", status_code=201)
    def create(project_id: str, body: AutomationInput):
        return scheduler.save(context(project_id, "version:approve"), body)

    @app.get(prefix + "/automations/{identifier}")
    def read(project_id: str, identifier: str):
        return scheduler.read(context(project_id), identifier)

    @app.post(prefix + "/automations/{identifier}")
    def save(project_id: str, identifier: str, body: AutomationInput):
        return scheduler.save(context(project_id, "version:approve"), body, identifier)

    @app.post(prefix + "/automations/{identifier}/approve")
    def approve(project_id: str, identifier: str, body: AutomationDecision):
        return scheduler.approve(
            context(project_id, "version:approve"), identifier, body
        )

    @app.post(prefix + "/automations/{identifier}/state")
    def state(project_id: str, identifier: str, body: AutomationStateInput):
        return scheduler.state(context(project_id, "version:approve"), identifier, body)

    @app.post(prefix + "/automations/{identifier}/run")
    async def manual(project_id: str, identifier: str, body: ManualOccurrence):
        return await scheduler.manual(
            context(project_id, "version:approve"), identifier, body
        )

    @app.get(prefix + "/automations/{identifier}/occurrences")
    def occurrences(
        project_id: str,
        identifier: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        query_keys(request, {"after", "limit"})
        return scheduler.inventory(
            context(project_id),
            AutomationOccurrenceModel,
            identifier=identifier,
            after=after,
            limit=limit,
        )

    @app.get(prefix + "/automations/{identifier}/events")
    def events(
        project_id: str,
        identifier: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        query_keys(request, {"after", "limit"})
        return scheduler.inventory(
            context(project_id),
            AutomationEventModel,
            identifier=identifier,
            after=after,
            limit=limit,
        )

    @app.post(
        prefix + "/automations/{identifier}/occurrences/{occurrence_id}/reconcile"
    )
    def reconcile(
        project_id: str, identifier: str, occurrence_id: str, body: ReconcileOccurrence
    ):
        return scheduler.reconcile(
            context(project_id, "version:approve"), identifier, occurrence_id, body
        )

    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            stopped = asyncio.Event()

            async def run():
                while not stopped.is_set():
                    try:
                        await scheduler.tick()
                    except ExecutionOwnershipError:
                        scheduler.last_error = "execution_ownership_lost"
                        return  # No timer-driven takeover of a stale authority.
                    except Exception:
                        scheduler.last_error = "scheduling_unavailable"
                        logging.getLogger("aryn.core.automations").error(
                            "core_automation_tick_unavailable"
                        )
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(stopped.wait(), timeout=15)

            task = None if testing else asyncio.create_task(run())
            try:
                yield
            finally:
                stopped.set()
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

    app.router.lifespan_context = lifespan
