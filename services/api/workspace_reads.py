"""Bounded, authorized workspace projections; never a governance authority."""
import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import defer

from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.audit_repo import AuditRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.budget_repo import BudgetRepository
from database.repositories.run_state_repo import RunStateRepository
from database.repositories.exceptions import EntityNotFoundError, InvalidStateTransitionError
from modules.bench.quality_gate import QualityGateFailedError
from database.schema import (
    AgentAssignmentModel, AgentBlueprintModel, AgentVersionModel, AuditEventModel,
    BenchEvaluationModel, DivisionModel, MembershipModel, ProjectMembershipModel,
    ProjectModel, RunStateModel,
)
from modules.core.errors import sanitize
from packages.contracts.agent import AgentVersion
from packages.contracts.workspace import Attention, Metric, ResourceItem, ResourcePage, WorkspaceSummary


def timestamp(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat()


RESOURCES = {
    "projects": (ProjectModel, ProjectModel.created_at, {""}),
    "divisions": (DivisionModel, DivisionModel.created_at, {""}),
    "blueprints": (AgentBlueprintModel, AgentBlueprintModel.created_at, {""}),
    "assignments": (AgentAssignmentModel, AgentAssignmentModel.created_at, {"", "active", "inactive"}),
    "runs": (RunStateModel, RunStateModel.created_at, {"", "queued", "started", "running", "stopping", "completed", "failed", "cancelled", "outcome_unknown"}),
    "versions": (AgentVersionModel, AgentVersionModel.created_at, {"", "draft", "evaluating", "approved", "published", "deprecated", "rejected"}),
    "evaluations": (BenchEvaluationModel, BenchEvaluationModel.evaluated_at, {"", "passed", "failed"}),
    "audits": (AuditEventModel, AuditEventModel.occurred_at, {"", "attempted", "allowed", "denied", "completed", "failed", "cancelled"}),
}


class WorkspaceReads:
    def __init__(self, db, permissions, coordinator):
        self.db, self.permissions, self.coordinator = db, permissions, coordinator
        self.cursor_key = secrets.token_bytes(32)

    def authorize(self, session, context):
        self.permissions.enforce("run:read", context, context.organization_id, context.project_id, session=session)

    def query(self, session, context, resource):
        model = RESOURCES[resource][0]
        query = session.query(model)
        if resource == "versions":
            return query.join(AgentBlueprintModel).filter(AgentBlueprintModel.organization_id == context.organization_id,
                AgentBlueprintModel.project_id == context.project_id)
        query = query.filter(model.organization_id == context.organization_id)
        if resource != "projects":
            query = query.filter(model.project_id == context.project_id)
        else:
            member = session.query(MembershipModel).filter_by(organization_id=context.organization_id,
                user_id=context.actor.actor_id, status="active").one()
            if member.role.lower() != "admin":
                query = query.join(ProjectMembershipModel, ProjectMembershipModel.project_id == ProjectModel.id).filter(
                    ProjectMembershipModel.organization_id == context.organization_id,
                    ProjectMembershipModel.user_id == context.actor.actor_id,
                    ProjectMembershipModel.status == "active", ProjectMembershipModel.role.in_(["operator", "viewer"]))
        if resource == "runs":
            query = query.filter(RunStateModel.execution_mode != "bench").options(defer(RunStateModel.prompt), defer(RunStateModel.output))
        return query

    def encode_cursor(self, payload):
        encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
        return encoded + "." + hmac.new(self.cursor_key, encoded.encode(), hashlib.sha256).hexdigest()

    def decode_cursor(self, cursor, binding):
        try:
            encoded, signature = cursor.split(".")
            expected = hmac.new(self.cursor_key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            value = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if value["binding"] != binding or value["expires"] < dt.datetime.now(dt.timezone.utc).timestamp():
                raise ValueError("scope")
            return dt.datetime.fromisoformat(value["time"]), value["id"]
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, "Invalid or expired scoped cursor.") from exc

    def item(self, session, context, resource, record):
        _, order, _ = RESOURCES[resource]
        item = ResourceItem(id=record.id, organization_id=context.organization_id,
            project_id=record.id if resource == "projects" else context.project_id,
            name=getattr(record, "name", None) or (record.event_type if resource == "audits" else record.id),
            created_at=timestamp(getattr(record, order.key)), status=getattr(record, "status", None),
            slug=getattr(record, "slug", None), description=getattr(record, "description", None),
            generation=getattr(record, "generation", None))
        if resource == "audits":
            item.verified = AuditRepository(session).verify_authenticated_event(record)
            item.verification_reason = "authenticated_event" if item.verified else "legacy_or_unverified_audit"
            item.references = {"actor_id": record.actor_id, "resource_id": record.resource_id, "correlation_id": record.correlation_id}
        elif resource == "versions":
            registry = AgentActivationRepository(session, self.db.evidence_signer, self.permissions).registry_entry(context, record)
            item.name = record.version_number
            item.verified = registry.rollback_eligible if record.status == "published" else registry.bench_verified
            item.verification_reason = registry.reason
            item.references = {"blueprint_id": record.blueprint_id, "model": record.model,
                "payload_hash": record.payload_hash, "registry": registry.model_dump(mode="json")}
        elif resource == "runs":
            repo = RunStateRepository(session)
            item.verified = False
            try:
                claim = repo.verify_execution_claim(record)
                provenance = repo.verify_assignment_provenance(record)
                item.verified = bool(claim and (not record.assignment_id or provenance))
            except (ValueError, RuntimeError, InvalidStateTransitionError):
                pass
            item.verification_reason = "verified_captured_claim" if item.verified else "unverified_execution_provenance"
            item.references = {"model": record.actual_model, "agent_version_id": record.agent_version_id,
                "usage_availability": record.usage_availability, "total_tokens": record.total_tokens if item.verified and record.usage_availability == "measured" else None}
        elif resource == "evaluations":
            item.status = "passed" if record.passed else "failed"
            item.verified = False
            version = self.query(session, context, "versions").filter(AgentVersionModel.id == record.version_id).first()
            if version:
                try:
                    BenchRepository(session, self.db.evidence_signer).validate_stored(context, record, AgentVersion.from_stored(version))
                    item.verified = True
                except (ValueError, RuntimeError, QualityGateFailedError):
                    pass
            item.verification_reason = "verified_bench_evidence" if item.verified else "unverified_bench_evidence"
            item.references = {"version_id": record.version_id}
        elif resource == "assignments":
            item.name = record.role_name
            item.references = {"blueprint_id": record.blueprint_id, "version_id": record.version_id, "division_id": record.division_id}
        return item

    def page(self, context, resource, *, limit=25, cursor=None, q="", status="", sort="newest", actor="", resource_id=""):
        if resource not in RESOURCES:
            raise HTTPException(404, "Resource unavailable.")
        model, order, statuses = RESOURCES[resource]
        if status not in statuses or sort not in {"newest", "oldest"} or ((actor or resource_id) and resource != "audits"):
            raise HTTPException(422, "Unsupported filter or ordering.")
        binding = [context.organization_id, context.project_id, context.actor.actor_id, resource, limit, q, status, sort, actor, resource_id]
        with self.db.session() as session:
            self.authorize(session, context)
            query = self.query(session, context, resource)
            if q:
                field = getattr(model, "name", None)
                if field is None:
                    field = model.event_type if resource == "audits" else model.model if resource in {"versions", "runs"} else model.id
                query = query.filter(func.lower(field).contains(q.lower(), autoescape=True))
            if status:
                query = query.filter(model.passed == (status == "passed")) if resource == "evaluations" else query.filter(model.status == status)
            if actor:
                query = query.filter(model.actor_id == actor)
            if resource_id:
                query = query.filter(model.resource_id == resource_id)
            if cursor:
                time, identifier = self.decode_cursor(cursor, binding)
                older = sort == "newest"
                query = query.filter(or_(order < time if older else order > time,
                    and_(order == time, model.id < identifier if older else model.id > identifier)))
            rows = query.order_by(order.desc() if sort == "newest" else order.asc(),
                model.id.desc() if sort == "newest" else model.id.asc()).limit(limit + 1).all()
            items = [self.item(session, context, resource, record) for record in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = self.encode_cursor({"binding": binding, "time": timestamp(getattr(last, order.key)),
                    "id": last.id, "expires": dt.datetime.now(dt.timezone.utc).timestamp() + 3600})
            self.authorize(session, context)
            result = ResourcePage[ResourceItem](organization_id=context.organization_id, project_id=context.project_id,
                resource=resource, items=items, next_cursor=next_cursor, limit=limit, refreshed_at=timestamp(dt.datetime.now(dt.timezone.utc)))
            return sanitize(result.model_dump(mode="json"), credentials=getattr(self.db, "protected_credentials", ()))

    def detail(self, context, resource, identifier):
        if resource not in RESOURCES:
            raise HTTPException(404)
        model = RESOURCES[resource][0]
        with self.db.session() as session:
            self.authorize(session, context)
            record = self.query(session, context, resource).filter(model.id == identifier).first()
            if record is None:
                raise EntityNotFoundError("Resource unavailable in this scope.")
            item = self.item(session, context, resource, record)
            if resource == "projects":
                target = self.permissions.identity_binder.create_trusted_context(context.actor.actor_id,
                    context.organization_id, record.id, auth_session_id=context.auth_session_id)
                self.authorize(session, target)
                item.references = {"division_count": self.query(session, target, "divisions").count()}
            elif resource == "divisions":
                item.references = {"assignment_count": self.query(session, context, "assignments").filter(AgentAssignmentModel.division_id == identifier).count()}
            elif resource == "runs":
                if item.verified:
                    item.references["result"] = self.coordinator.stored_result(RunStateRepository(session).get_run(context, identifier)).model_dump(mode="json")
            elif resource == "audits":
                # Explicit safe envelope. Private signing material never crosses API.
                item.references["redacted_payload"] = sanitize(json.loads(record.redacted_payload_json), audit=True, credentials=getattr(self.db, "protected_credentials", ()))
                item.references["integrity_reference"] = record.integrity_reference
            self.authorize(session, context)
            return sanitize(item.model_dump(mode="json"), credentials=getattr(self.db, "protected_credentials", ()))

    def summary(self, context):
        with self.db.session() as session:
            self.authorize(session, context)
            counts = {name: self.query(session, context, resource).count() for name, resource in
                [("blueprints", "blueprints"), ("runs", "runs"), ("audits", "audits"), ("divisions", "divisions"), ("evaluations", "evaluations")]}
            counts["published"] = self.query(session, context, "versions").filter(AgentVersionModel.status == "published").count()
            counts["assigned"] = self.query(session, context, "assignments").filter(AgentAssignmentModel.status == "active").count()
            definitions = {"blueprints": "Blueprint tersimpan dalam proyek", "runs": "Run tersimpan selain eksekusi Bench",
                "audits": "Peristiwa audit tersimpan; autentikasi diperiksa pada item", "divisions": "Division tersimpan dalam proyek",
                "evaluations": "Evaluasi Bench tersimpan", "published": "Versi berstatus published; kelayakan governance diperiksa pada detail",
                "assigned": "Assignment berstatus active; berbeda dari versi published dan run aktif"}
            metrics = {name: Metric(value=value, definition=definitions[name], source="Core scoped SQL inventory") for name, value in counts.items()}
            attention = []
            for status, description in [("outcome_unknown", "Hasil tidak pasti; reservation dipertahankan, tinjau sebelum mengulang"),
                ("failed", "Run gagal tersimpan; telusuri error dan evidence")]:
                problem_runs = self.query(session, context, "runs").filter(RunStateModel.status == status)
                count = problem_runs.count()
                if count:
                    latest_problem = problem_runs.order_by(RunStateModel.created_at.desc(), RunStateModel.id.desc()).first()
                    attention.append(Attention(code=status, count=count, description=description,
                        route="/runs/" + quote(latest_problem.id, safe="")))
            latest = {}
            for resource in ("runs", "audits"):
                model, order, _ = RESOURCES[resource]
                records = self.query(session, context, resource).order_by(order.desc(), model.id.desc()).limit(5).all()
                latest[resource] = [self.item(session, context, resource, record) for record in records]
            reviews = self.query(session, context, "versions").filter(AgentVersionModel.status == "draft",
                AgentVersionModel.evaluation_id.is_not(None)).order_by(AgentVersionModel.created_at.desc(), AgentVersionModel.id.desc()).limit(5).all()
            candidates = [self.item(session, context, "versions", record) for record in reviews]
            candidates = [item for item in candidates if item.verified and item.references["registry"]["bench_passed"]]
            metrics["review_candidates"] = Metric(value=len(candidates), definition="Candidate terbaru dengan Bench terverifikasi; maksimal 5, bukan total queue", source="Core Bench verification (bounded)", verification="verified_bounded")
            if candidates:
                attention.append(Attention(code="review", count=len(candidates), description="Candidate terbaru dengan Bench terverifikasi perlu tinjauan Core", route="/approvals"))
            budget = BudgetRepository(session).get_budget(context)
            budget_data = {key: getattr(budget, key) for key in ("max_tokens_per_run", "cumulative_tokens", "reserved_tokens")} if budget else None
            capabilities = {action: self.permissions.evaluate(action, context, context.organization_id, context.project_id, session=session).allowed
                for action in ("blueprint:create", "run:create", "version:approve", "version:publish", "agent:assign", "division:manage")}
            self.authorize(session, context)
            result = WorkspaceSummary(organization_id=context.organization_id, project_id=context.project_id,
                refreshed_at=timestamp(dt.datetime.now(dt.timezone.utc)), metrics=metrics, permissions=capabilities,
                attention=attention, latest_runs=latest["runs"], latest_audits=latest["audits"], review_candidates=candidates,
                budget=budget_data, usage={"availability": "measured" if budget else "unavailable",
                    "tokens": budget.cumulative_tokens if budget else None, "cost_usd": None,
                    "cost_source": "unavailable", "entitlement": "unknown", "source": "Core usage ledger; no provider hard cap or billing claim"})
            return sanitize(result.model_dump(mode="json"), credentials=getattr(self.db, "protected_credentials", ()))
