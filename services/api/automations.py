"""Scoped scheduling routes and the single Core owner's application lifespan."""

import asyncio
import logging
import json
import time
from collections import deque
from contextlib import asynccontextmanager, suppress
from fastapi import Query, Request, HTTPException
from fastapi.responses import JSONResponse
from modules.core.automations.webhook import WebhookIngress
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
    WebhookSignal,
    WebhookCredentialAction,
    AutomationTarget,
)


def register_automations(
    app, coordinator, context, require_runtime, *, testing=False, local=True, ingress_origin=""
):
    scheduler = CoreAutomations(coordinator, require_runtime=require_runtime)
    scheduler.recover()
    app.state.automations = scheduler
    capabilities = Capabilities(coordinator)
    prefix = "/api/projects/{project_id}"
    webhook = WebhookIngress(scheduler)
    ingress_attempts = deque(maxlen=60)

    def public(record):
        # Credential hashes/issuance state remain protected Core metadata.
        credential = record.get("webhook_credential")
        return {k: v for k, v in record.items() if k != "webhook_credential"} | {"webhook": {"id": credential["id"], "url": ingress_origin + "/ingress/webhooks/" + credential["id"]} if credential and ingress_origin else None}

    @app.get(prefix + "/automation-triggers")
    def triggers(project_id: str):
        context(project_id)
        return {"organization_id": context(project_id).organization_id, "project_id": project_id,
            "mode": "local" if local else "hosted", "webhook_available": bool(ingress_origin),
            "webhook_reason": None if ingress_origin else "hosted_https_ingress_required",
            "webhook_authentication": "scoped_bearer_over_tls", "mcp_available": False,
            "kinds": ["interval", "daily", "weekly", "cron", "webhook"], "scheduler": scheduler.status()}

    @app.post(prefix + "/automations/{identifier}/webhook")
    def credential(project_id: str, identifier: str, body: WebhookCredentialAction):
        ctx = context(project_id, "version:approve")
        if not ingress_origin:
            raise HTTPException(503, "Configured Hosted HTTPS ingress required.")
        value = webhook.credential(ctx, identifier, body)
        return JSONResponse(value | {"url": ingress_origin + "/ingress/webhooks/" + value["id"]}, headers={"Cache-Control": "no-store"})

    @app.post("/ingress/webhooks/{identifier}")
    async def external_signal(identifier: str, request: Request):
        if not ingress_origin:
            raise HTTPException(503, "Webhook ingress unavailable.")
        now = time.monotonic()
        if len(ingress_attempts) >= 60 and now - ingress_attempts[0] < 60:
            raise HTTPException(429, "Ingress rate limit exceeded.")
        ingress_attempts.append(now)
        if not getattr(request.state,"secure_transport_verified",False) or request.headers.get("host") != ingress_origin.split("//", 1)[1] or request.headers.get("cookie") or request.headers.get("origin"):
            raise HTTPException(403, "Webhook transport rejected.")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(415, "JSON required.")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 4096:
                raise HTTPException(413, "Webhook payload exceeds limit.")
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer ") or not 32 <= len(authorization[7:]) <= 128:
            raise HTTPException(401, "Webhook authentication failed.")
        try:
            def unique_pairs(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("Duplicate key")
                    value[key] = item
                return value
            signal = WebhookSignal.model_validate(json.loads(data, object_pairs_hook=unique_pairs))
            body_text = json.dumps(signal.model_dump(), ensure_ascii=False)
            if authorization[7:] in body_text or any(value and value in body_text for value in getattr(coordinator.db_manager,"protected_credentials",())):
                raise ValueError("Credential in event data")
        except ValueError:
            raise HTTPException(422, "Webhook signal rejected.") from None
        occurrence, fresh = webhook.accept(identifier, authorization[7:], request.headers.get("x-aryn-timestamp", ""), signal)
        return JSONResponse({"accepted": fresh, "occurrence_id": occurrence["id"], "status": occurrence["status"]}, status_code=202 if fresh else 200,
            headers={"Cache-Control": "no-store"})

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
            "instants": [] if body.schedule.kind == "webhook" else preview(body.schedule, scheduler.clock()),
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
        ctx = context(project_id, "version:approve")
        return {"organization_id":ctx.organization_id,"project_id":project_id,**scheduler.targets(ctx, kind, after, limit)}

    @app.post(prefix + "/automation-targets/check")
    def check_target(project_id: str, body: AutomationTarget):
        ctx = context(project_id, "version:approve")
        scheduler.preflight_target(ctx, body)
        return {"organization_id":ctx.organization_id,"project_id":project_id,"target": body.model_dump(mode="json"), "available": True, "label": body.id, "reason": None}

    @app.get(prefix + "/automations")
    def definitions(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
        q: str = Query("", max_length=160),
        status: str = Query("", pattern=r"^(|enabled|paused)$"),
        trigger: str = Query("", pattern=r"^(|interval|daily|weekly|cron|webhook)$"),
    ):
        query_keys(request, {"after", "limit", "q", "status", "trigger"})
        ctx = context(project_id)
        return {
            **(page := scheduler.inventory(ctx, after=after, limit=limit, q=q, status=status, trigger=trigger)),
            "items": [public(scheduler.read(ctx, item["id"])) for item in page["items"]],
            "scheduler": scheduler.status(),
        }

    @app.post(prefix + "/automations", status_code=201)
    def create(project_id: str, body: AutomationInput):
        if body.schedule.kind == "webhook" and not ingress_origin:
            raise HTTPException(503, "Configured Hosted HTTPS ingress required.")
        return public(scheduler.save(context(project_id, "version:approve"), body))

    @app.get(prefix + "/automations/{identifier}")
    def read(project_id: str, identifier: str):
        return public(scheduler.read(context(project_id), identifier))

    @app.post(prefix + "/automations/{identifier}")
    def save(project_id: str, identifier: str, body: AutomationInput):
        if body.schedule.kind == "webhook" and not ingress_origin:
            raise HTTPException(503, "Configured Hosted HTTPS ingress required.")
        return public(scheduler.save(context(project_id, "version:approve"), body, identifier))

    @app.post(prefix + "/automations/{identifier}/approve")
    def approve(project_id: str, identifier: str, body: AutomationDecision):
        return scheduler.approve(
            context(project_id, "version:approve"), identifier, body
        )

    @app.post(prefix + "/automations/{identifier}/state")
    def state(project_id: str, identifier: str, body: AutomationStateInput):
        return public(scheduler.state(context(project_id, "version:approve"), identifier, body))

    @app.post(prefix + "/automations/{identifier}/run")
    async def manual(project_id: str, identifier: str, body: ManualOccurrence, request: Request):
        return await scheduler.manual(
            context(project_id, "version:approve"), identifier, body, defer=request.headers.get("Prefer") == "respond-async"
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
