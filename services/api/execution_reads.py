"""Bounded unified observation, without duplicating Core or Workflow ledgers."""

import datetime as dt
import json
from fastapi import HTTPException
from sqlalchemy import select, union_all, literal, func, and_, or_, cast, JSON
from database.schema import (
    RunStateModel as Run,
    WorkflowRunModel as WorkflowRun,
    WorkflowDefinitionModel as Workflow,
    AgentBlueprintModel as Blueprint,
    AgentVersionModel as Version,
    ConversationTurnModel as Chat,
    AuditEventModel as Audit,
    AutomationOccurrenceModel as Occurrence,
    AutomationDefinitionModel as Automation,
)
from database.repositories.run_state_repo import RunStateRepository
from database.repositories.audit_repo import AuditRepository
from database.repositories.exceptions import EntityNotFoundError
from modules.core.workflows.executor import WorkflowExecutor
from modules.core.errors import sanitize
from services.api.workspace_reads import timestamp


class ExecutionReads:
    def __init__(self, workspace, editor):
        self.reads, self.db, self.core = workspace, workspace.db, workspace.coordinator
        self.workflows = WorkflowExecutor(self.core)
        self.editor = editor

    def field(self, column, name):
        return (
            func.json_extract(column, "$." + name)
            if self.db.engine.dialect.name == "sqlite"
            else cast(column, JSON)[name].as_string()
        )

    def candidates(self, ctx):
        preview_owned = (
            select(Audit.id)
            .where(
                Audit.resource_id == Run.id,
                Audit.organization_id == ctx.organization_id,
                Audit.project_id == ctx.project_id,
                Audit.actor_id == ctx.actor.actor_id,
                Audit.event_type == "factory.preview.accepted",
            )
            .exists()
        )
        agent = (
            select(
                Run.id.label("id"),
                Run.created_at.label("time"),
                literal("agent").label("kind"),
                func.coalesce(Blueprint.name, Run.id).label("name"),
                Run.status.label("status"),
            )
            .outerjoin(Version, Version.id == Run.agent_version_id)
            .outerjoin(Blueprint, Blueprint.id == Version.blueprint_id)
            .where(
                Run.organization_id == ctx.organization_id,
                Run.project_id == ctx.project_id,
                Run.execution_mode.in_(["direct", "async", "agent_preview"]),
                ~select(Chat.id).where(Chat.run_id == Run.id).exists(),
                self.field(Run.assignment_provenance_json, "workflow").is_(None),
                or_(Run.execution_mode != "agent_preview", preview_owned),
            )
        )
        workflow = (
            select(
                WorkflowRun.id.label("id"),
                WorkflowRun.created_at.label("time"),
                literal("workflow").label("kind"),
                self.field(Workflow.details_json, "name").label("name"),
                WorkflowRun.status.label("status"),
            )
            .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
            .where(
                WorkflowRun.organization_id == ctx.organization_id,
                WorkflowRun.project_id == ctx.project_id,
            )
        )
        return union_all(agent, workflow).subquery()

    def catalog(
        self,
        ctx,
        *,
        q="",
        kind="",
        status="",
        after="",
        limit=25,
        order="desc",
        since=None,
        until=None,
    ):
        if since and until:
            from modules.core.automations.recurrence import instant

            try:
                if instant(since) > instant(until):
                    raise HTTPException(422, "Start must precede end.")
            except ValueError:
                raise HTTPException(422, "Offset-aware time required.") from None
        binding = [
            "executions",
            ctx.organization_id,
            ctx.project_id,
            ctx.actor.actor_id,
            q,
            kind,
            status,
            order,
            since,
            until,
        ]
        with self.db.session() as session:
            self.reads.authorize(session, ctx)
            c = self.candidates(ctx)
            query = select(c)
            if q:
                term = (
                    "%"
                    + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    + "%"
                )
                query = query.where(
                    or_(
                        c.c.name.ilike(term, escape="\\"),
                        c.c.id.ilike(term, escape="\\"),
                    )
                )
            if kind:
                query = query.where(c.c.kind == kind)
            if status:
                query = query.where(c.c.status == status)
            for value, is_lower in ((since, True), (until, False)):
                if value:
                    from modules.core.automations.recurrence import instant

                    try:
                        at = instant(value)
                    except ValueError:
                        raise HTTPException(
                            422, "Offset-aware time required."
                        ) from None
                    query = query.where(c.c.time >= at if is_lower else c.c.time <= at)
            key = c.c.kind + ":" + c.c.id
            if after:
                when, identifier = self.reads.decode_cursor(after, binding)
                query = query.where(
                    or_(
                        c.c.time < when if order == "desc" else c.c.time > when,
                        and_(
                            c.c.time == when,
                            key < identifier if order == "desc" else key > identifier,
                        ),
                    )
                )
            rows = session.execute(
                query.order_by(
                    c.c.time.desc() if order == "desc" else c.c.time.asc(),
                    key.desc() if order == "desc" else key.asc(),
                ).limit(limit + 1)
            ).all()
            items = [
                self.item(session, ctx, row.kind, row.id, row.name)
                for row in rows[:limit]
            ]
            cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                cursor = self.reads.encode_cursor(
                    {
                        "binding": binding,
                        "time": timestamp(last.time),
                        "id": last.kind + ":" + last.id,
                        "expires": dt.datetime.now(dt.timezone.utc).timestamp() + 3600,
                    }
                )
            self.reads.authorize(session, ctx)
            return {
                "organization_id": ctx.organization_id,
                "project_id": ctx.project_id,
                "items": items,
                "next_cursor": cursor,
            }

    def item(self, session, ctx, kind, identifier, name=None, detail=False):
        source, references, timeline, io, usage = "manual", {}, [], None, None
        if kind == "workflow":
            row, payload = self.workflows.get(session, WorkflowRun, ctx, identifier)
            version = self.workflows.version(session, ctx, payload["version_id"])
            _, definition = self.workflows.get(
                session, Workflow, ctx, payload["workflow_id"]
            )
            name, verified, status = definition["name"], True, payload["status"]
            references = {
                "workflow_id": payload["workflow_id"],
                "version_id": version.id,
                "digest": version.digest,
                "artifact_id": payload["artifact_id"],
            }
            origin = payload.get("automation_reference")
            created, completed, duration = timestamp(row.created_at), None, None
            if detail:
                io = {"input": payload["input"], "output": None}
                timeline = payload["tasks"]
        else:
            row = RunStateRepository(session).get_run(ctx, identifier)
            if (
                row.execution_mode not in {"direct", "async", "agent_preview"}
                or session.query(Chat.id).filter_by(run_id=identifier).first()
            ):
                raise EntityNotFoundError("Private execution unavailable in Runs.")
            provenance = json.loads(row.assignment_provenance_json or "{}")
            if provenance.get("workflow"):
                raise EntityNotFoundError(
                    "Workflow task is inspected through its parent run."
                )
            result = self.core.stored_result(row)
            verified, status = result.execution_claim_verified, row.status
            origin = provenance.get("automation")
            created, completed = (
                timestamp(row.created_at),
                timestamp(row.completed_at) if row.completed_at else None,
            )
            duration = (
                result.completed_at - result.created_at
                if result.completed_at is not None
                and result.completed_at >= result.created_at
                and status != "outcome_unknown"
                else None
            )
            references = {
                "assignment_id": row.assignment_id,
                "agent_version_id": row.agent_version_id,
            }
            if row.execution_mode == "agent_preview":
                accepted = (
                    session.query(Audit)
                    .filter_by(
                        resource_id=identifier,
                        organization_id=ctx.organization_id,
                        project_id=ctx.project_id,
                        event_type="factory.preview.accepted",
                        actor_id=ctx.actor.actor_id,
                    )
                    .first()
                )
                if not accepted or not AuditRepository(
                    session
                ).verify_authenticated_event(accepted):
                    raise EntityNotFoundError(
                        "Preview is private to its initiating actor."
                    )
                blueprint = json.loads(accepted.redacted_payload_json).get(
                    "blueprint_id"
                )
                # Reuse the existing Blueprint/Working Copy authorization.
                self.editor.authorize(session, ctx, blueprint)
                source, references["blueprint_id"] = "agent_preview", blueprint
            elif row.assignment_id:
                source = "agent_factory"
                version = session.get(Version, row.agent_version_id)
                blueprint = (
                    session.get(Blueprint, version.blueprint_id) if version else None
                )
                if (
                    blueprint
                    and blueprint.organization_id == ctx.organization_id
                    and blueprint.project_id == ctx.project_id
                ):
                    name, references["blueprint_id"] = blueprint.name, blueprint.id
            if detail:
                io = {
                    "input": sanitize(row.prompt) if verified else None,
                    "output": result.output
                    if verified and row.output is not None
                    else None,
                }
                usage = result.usage.model_dump(mode="json") if verified else None
                references |= {
                    "requested_model": result.requested_model,
                    "actual_model": result.actual_model,
                    "provider": result.provider,
                    "runtime": result.runtime_backend,
                    "gateway": result.gateway,
                    "error_code": result.error_code,
                }
                events = (
                    session.query(Audit)
                    .filter_by(
                        resource_id=identifier,
                        organization_id=ctx.organization_id,
                        project_id=ctx.project_id,
                    )
                    .order_by(Audit.occurred_at, Audit.id)
                    .limit(100)
                    .all()
                )
                timeline = [
                    {
                        "id": e.id,
                        "event": e.event_type,
                        "status": e.status,
                        "occurred_at": timestamp(e.occurred_at),
                    }
                    for e in events
                    if AuditRepository(session).verify_authenticated_event(e)
                ]
        if origin:
            from modules.core.records import SignedRecords

            records = SignedRecords(self.core)
            _, occurrence = records.get(
                session, Occurrence, ctx, origin["occurrence_id"]
            )
            if (
                occurrence["run_id"] != identifier
                or occurrence["automation_id"] != origin["automation_id"]
                or occurrence["run_kind"] != kind
            ):
                raise HTTPException(409, "Automation execution lineage differs.")
            _, automation = records.get(
                session, Automation, ctx, origin["automation_id"]
            )
            references |= {
                "automation_id": automation["id"],
                "occurrence_id": occurrence["id"],
            }
            source = "automation"
        item = {
            "id": identifier,
            "kind": kind,
            "name": name or identifier,
            "organization_id": ctx.organization_id,
            "project_id": ctx.project_id,
            "status": status,
            "source": source,
            "created_at": created,
            "completed_at": completed,
            "duration_seconds": duration,
            "verified": verified,
            "references": references,
        }
        if detail:
            item |= {
                "timeline": timeline,
                "io": io,
                "usage": usage,
                "workflow_run": payload if kind == "workflow" else None,
                "workflow_version": version.model_dump(mode="json")
                if kind == "workflow"
                else None,
                "permissions": {
                    a: self.core.permission_engine.evaluate(
                        a, ctx, ctx.organization_id, ctx.project_id, session=session
                    ).allowed
                    for a in ("run:cancel", "run:trace")
                },
            }
        return sanitize(item, credentials=getattr(self.db, "protected_credentials", ()))

    def detail(self, ctx, kind, identifier):
        with self.db.session() as session:
            self.reads.authorize(session, ctx)
            result = self.item(session, ctx, kind, identifier, detail=True)
            self.reads.authorize(session, ctx)
            if kind == "workflow":
                # Owner identifiers/request hashes are internal, never a UI trace.
                result["workflow_run"] = {
                    k: v
                    for k, v in result["workflow_run"].items()
                    if k not in {"owner_id", "request_hash", "actor_id"}
                }
            return result
