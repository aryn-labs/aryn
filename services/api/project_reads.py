"""Bounded Projects projections over existing, verified governance records.

This is a catalog projection, never a second artifact store or execution authority.
Chat turns remain actor-private and are excluded from project work/output lists.
"""
import json
import datetime as dt
from fastapi import HTTPException
from sqlalchemy import select, union_all, literal, and_, or_, func, cast, JSON
from database.schema import (AgentBlueprintModel as Blueprint, AgentVersionModel as Version,
    AgentAssignmentModel as Assignment, DivisionModel as Division, ProjectMembershipModel as Member,
    MembershipModel as OrgMember, RunStateModel as Run, ConversationTurnModel as ChatTurn,
    WorkflowDefinitionModel as Workflow, WorkflowRunModel as WorkflowRun,
    WorkflowArtifactModel as Artifact, BenchEvaluationModel as Evaluation, AuditEventModel as Audit)
from database.repositories.exceptions import EntityNotFoundError
from modules.core.errors import sanitize
from modules.core.workflows.executor import WorkflowExecutor
from services.api.workspace_reads import timestamp

MODELS = {"workflow": Workflow, "workflow-run": WorkflowRun, "run": Run, "artifact": Artifact,
    "evaluation": Evaluation, "assignment": Assignment, "division": Division, "member": Member, "audit": Audit}
COLLECTIONS = {"work": {"workflow", "workflow-run", "run"},
    "team": {"assignment", "division", "member"}, "results": {"artifact", "evaluation", "run"}, "activity": {"audit"}}


class ProjectReads:
    def __init__(self, reads):
        self.reads, self.db = reads, reads.db
        self.executor = WorkflowExecutor(reads.coordinator)

    def field(self, column, key):
        return func.json_extract(column, "$." + key) if self.db.engine.dialect.name == "sqlite" else cast(column, JSON)[key].as_string()

    def candidates(self, session, ctx, collection, q, format):
        statements = []
        for kind in sorted(COLLECTIONS[collection]):
            cls = MODELS[kind]
            when = cls.evaluated_at if kind == "evaluation" else cls.occurred_at if kind == "audit" else cls.created_at
            title = literal("")
            result_format = literal(kind)
            statement = select(cls.id.label("id"), when.label("time"), literal(kind).label("kind"))
            if kind == "run":
                statement = statement.outerjoin(Version, Version.id == Run.agent_version_id).outerjoin(Blueprint, Blueprint.id == Version.blueprint_id)
                title = Blueprint.name
                statement = statement.where(Run.execution_mode != "bench", ~select(ChatTurn.id).where(ChatTurn.run_id == Run.id).exists())
                if collection == "results":
                    statement = statement.where(Run.status == "completed", Run.output.is_not(None), Run.output != "")
                    statement = statement.where(~select(Artifact.id).where(Artifact.organization_id == ctx.organization_id,
                        Artifact.project_id == ctx.project_id, self.field(Artifact.details_json, "core_run_id") == Run.id).exists())
                    result_format = literal("text")
            elif kind in {"workflow", "workflow-run", "artifact"}:
                if kind == "workflow":
                    title = self.field(Workflow.details_json, "name")
                else:
                    if kind == "artifact":
                        statement = statement.join(WorkflowRun, WorkflowRun.id == Artifact.workflow_run_id)
                        statement = statement.where(or_(self.field(Artifact.details_json, "core_run_id").is_not(None),
                            self.field(Artifact.details_json, "source_artifact_id").is_not(None)))
                        result_format = self.field(Artifact.details_json, "schema_name")
                    statement = statement.join(Workflow, Workflow.id == WorkflowRun.workflow_id)
                    title = self.field(Workflow.details_json, "name")
            elif kind == "evaluation":
                statement = statement.join(Version, Version.id == Evaluation.version_id).join(Blueprint, Blueprint.id == Version.blueprint_id)
                title = Blueprint.name
            elif kind == "assignment":
                statement = statement.join(Blueprint, Blueprint.id == Assignment.blueprint_id)
                title = Blueprint.name
            elif kind == "division":
                title = Division.name
            elif kind == "member":
                statement = statement.join(OrgMember, and_(OrgMember.organization_id == Member.organization_id, OrgMember.user_id == Member.user_id)).where(OrgMember.status == "active", Member.status == "active")
                title = Member.role
            else:
                title = Audit.event_type
            statement = statement.where(cls.organization_id == ctx.organization_id, cls.project_id == ctx.project_id)
            if q:
                statement = statement.where(func.lower(title).contains(q.casefold(), autoescape=True))
            if format:
                statement = statement.where(result_format == format)
            statements.append(statement)
        return union_all(*statements).subquery()

    def item(self, session, ctx, kind, record, detail=False):
        when = record.evaluated_at if kind == "evaluation" else record.occurred_at if kind == "audit" else record.created_at
        item = {"id": record.id, "organization_id": ctx.organization_id, "project_id": ctx.project_id,
            "kind": kind, "name": "", "status": getattr(record, "status", None), "created_at": timestamp(when),
            "description": None, "format": kind, "verified": None, "references": {}}
        if kind in {"workflow", "workflow-run", "artifact"}:
            _, payload = self.executor.get(session, type(record), ctx, record.id)
            item["verified"] = True
            if kind == "workflow":
                item["name"] = payload["name"]
                item["references"] = {"revision": payload["revision"]}
            elif kind == "workflow-run":
                _, definition = self.executor.get(session, Workflow, ctx, payload["workflow_id"])
                item["name"] = definition["name"]
                item["references"] = {"workflow_id": payload["workflow_id"], "version_id": payload["version_id"], "artifact_id": payload.get("artifact_id")}
                item["references"]["source_name"] = definition["name"]
            else:
                artifact, blob = self.executor.artifact(session, ctx, record.id)
                _, run = self.executor.get(session, WorkflowRun, ctx, artifact.workflow_run_id)
                _, definition = self.executor.get(session, Workflow, ctx, run["workflow_id"])
                item["name"] = definition["name"]
                item["format"] = artifact.schema_name
                item["status"] = run["status"]
                item["references"] = {"workflow_id": run["workflow_id"], "workflow_run_id": run["id"],
                    "version_id": run["version_id"], "core_run_id": artifact.core_run_id,
                    "agent_version_id": artifact.agent_version_id, "digest": artifact.digest,
                    "mime": artifact.mime, "length": artifact.length, "task_id": artifact.task_id,
                    "source_artifact_id": artifact.source_artifact_id, "model": artifact.model}
                item["references"]["source_name"] = definition["name"]
                if detail and artifact.mime == "application/json":
                    item["preview"] = {"kind": "text", "text": json.loads(blob)["text"]}
                # Studio prohibits framed documents. HTML remains metadata-only;
                # never weaken its CSP/X-Frame-Options to add a preview here.
        elif kind == "member":
            item["references"] = {"user_id": record.user_id, "role": record.role}
            item["name"] = ""
        else:
            resource = {"run": "runs", "evaluation": "evaluations", "assignment": "assignments", "division": "divisions", "audit": "audits"}[kind]
            source = self.reads.item(session, ctx, resource, record)
            item.update({"name": source.name if source.name != record.id else "", "status": source.status,
                "description": source.description, "verified": source.verified, "references": source.references})
            blueprint_id = source.references.get("blueprint_id")
            if kind in {"run", "evaluation"}:
                version_id = record.agent_version_id if kind == "run" else record.version_id
                version = session.query(Version).join(Blueprint).filter(Version.id == version_id,
                    Blueprint.organization_id == ctx.organization_id, Blueprint.project_id == ctx.project_id).first() if version_id else None
                blueprint_id = version.blueprint_id if version else None
                item["references"]["agent_version_id"] = version_id
                if version:
                    item["references"]["version_number"] = version.version_number
            if blueprint_id:
                blueprint = session.query(Blueprint).filter_by(id=blueprint_id, organization_id=ctx.organization_id, project_id=ctx.project_id).first()
                if blueprint:
                    item["name"] = blueprint.name
                    item["references"]["blueprint_id"] = blueprint.id
                    item["references"]["source_name"] = blueprint.name
            if kind == "run":
                item["format"] = "text"
                if detail and source.verified:
                    from database.repositories.run_state_repo import RunStateRepository
                    result = self.reads.coordinator.stored_result(RunStateRepository(session).get_run(ctx, record.id))
                    item["references"]["model"] = result.actual_model
                    item["references"]["requested_model"] = result.requested_model
                    if result.output and result.status.value == "completed":
                        item["preview"] = {"kind": "text", "text": result.output}
            elif kind == "audit" and detail:
                item["references"]["event_type"] = record.event_type
                item["references"]["redacted_payload"] = sanitize(json.loads(record.redacted_payload_json), audit=True, credentials=getattr(self.db, "protected_credentials", ()))
                item["references"]["integrity_reference"] = record.integrity_reference
            elif kind == "assignment":
                item["references"]["role_name"] = record.role_name
        return item

    def page(self, ctx, collection, limit=25, cursor=None, q="", format="", kind="", active_only=False):
        if collection not in COLLECTIONS or (format and collection != "results"):
            raise HTTPException(422)
        if (kind and kind not in COLLECTIONS[collection]) or (active_only and collection != "work"):
            raise HTTPException(422)
        binding = [ctx.organization_id, ctx.project_id, ctx.actor.actor_id, "project-" + collection, limit, q, format, kind, active_only]
        with self.db.session() as session:
            self.reads.authorize(session, ctx)
            candidates = self.candidates(session, ctx, collection, q, format)
            query = select(candidates)
            if kind:
                query = query.where(candidates.c.kind == kind)
            if active_only:
                query = query.where(or_(and_(candidates.c.kind == "run", candidates.c.id.in_(select(Run.id).where(Run.status.in_(["queued", "started", "running", "stopping"])))),
                    and_(candidates.c.kind == "workflow-run", candidates.c.id.in_(select(WorkflowRun.id).where(WorkflowRun.status.in_(["running", "waiting_review"]))))))
            if cursor:
                when, identifier = self.reads.decode_cursor(cursor, binding)
                query = query.where(or_(candidates.c.time < when, and_(candidates.c.time == when, (candidates.c.kind + ":" + candidates.c.id) < identifier)))
            rows = session.execute(query.order_by(candidates.c.time.desc(), candidates.c.kind.desc(), candidates.c.id.desc()).limit(limit + 1)).all()
            items = []
            for row in rows[:limit]:
                record = session.get(MODELS[row.kind], row.id)
                items.append(self.item(session, ctx, row.kind, record))
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = self.reads.encode_cursor({"binding": binding, "time": timestamp(last.time),
                    "id": last.kind + ":" + last.id, "expires": dt.datetime.now(dt.timezone.utc).timestamp() + 3600})
            formats = []
            if collection == "results":
                formats = [r[0] for r in session.execute(select(self.field(Artifact.details_json, "schema_name")).where(Artifact.organization_id == ctx.organization_id, Artifact.project_id == ctx.project_id,
                    or_(self.field(Artifact.details_json, "core_run_id").is_not(None), self.field(Artifact.details_json, "source_artifact_id").is_not(None))).distinct().limit(50)) if r[0]]
                unfiltered = self.candidates(session, ctx, "results", "", "")
                present = set(session.execute(select(unfiltered.c.kind).distinct()).scalars())
                formats = sorted(set(formats + (["text"] if "run" in present else []) + (["evaluation"] if "evaluation" in present else [])))
            self.reads.authorize(session, ctx)
            return sanitize({"organization_id": ctx.organization_id, "project_id": ctx.project_id, "items": items,
                "next_cursor": next_cursor, "formats": formats}, credentials=getattr(self.db, "protected_credentials", ()))

    def detail(self, ctx, kind, identifier):
        if kind not in MODELS:
            raise HTTPException(404)
        with self.db.session() as session:
            self.reads.authorize(session, ctx)
            record = session.query(MODELS[kind]).filter_by(id=identifier, organization_id=ctx.organization_id, project_id=ctx.project_id).first()
            if record is None:
                raise EntityNotFoundError("Project resource unavailable.")
            if kind == "run" and (record.execution_mode == "bench" or session.query(ChatTurn).filter_by(run_id=record.id).first()):
                raise EntityNotFoundError("Actor-private conversation output is not a project result.")
            if kind == "member" and not session.query(OrgMember).filter_by(organization_id=ctx.organization_id, user_id=record.user_id, status="active").first():
                raise EntityNotFoundError("Member unavailable.")
            result = self.item(session, ctx, kind, record, detail=True)
            self.reads.authorize(session, ctx)
            return sanitize(result, credentials=getattr(self.db, "protected_credentials", ()))
