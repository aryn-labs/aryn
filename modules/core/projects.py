"""Project metadata authority. No execution, grants, archive or deletion."""
import hashlib
import json
import re
import unicodedata
import uuid
import datetime as dt

from sqlalchemy import update

from database.repositories.exceptions import DuplicateEntityError, EntityNotFoundError, InvalidStateTransitionError
from database.schema import ProjectModel, ProjectMutationModel
from modules.core.audit.logger import AuditLogger
from packages.contracts.core import AuditStatus


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def project_view(record):
    def timestamp(value):
        return value.replace(tzinfo=dt.timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(dt.timezone.utc).isoformat()
    return {"id": record.id, "organization_id": record.organization_id, "name": record.name,
        "slug": record.slug, "description": record.description, "generation": record.generation,
        "created_at": timestamp(record.created_at), "updated_at": timestamp(record.updated_at)}


class ProjectService:
    def __init__(self, db, permissions):
        self.db, self.permissions = db, permissions
        self.audit = AuditLogger(db)

    def save(self, ctx, body, project_id=None):
        action = "project:update" if project_id else "project:create"
        if (project_id and ctx.project_id != project_id) or (not project_id and ctx.project_id):
            raise InvalidStateTransitionError("Project mutation scope differs.")
        fingerprint = hashlib.sha256(encode({"action": action, "project": project_id,
            "body": body.model_dump()}).encode()).hexdigest()
        with self.db.session(write=True) as session:
            self.permissions.enforce(action, ctx, ctx.organization_id, project_id, session=session)
            prior = session.query(ProjectMutationModel).filter_by(organization_id=ctx.organization_id,
                actor_id=ctx.actor.actor_id, idempotency_key=body.idempotency_key).first()
            if prior:
                envelope = {"organization_id": prior.organization_id, "project_id": prior.project_id,
                    "actor_id": prior.actor_id, "key": prior.idempotency_key,
                    "request_hash": prior.request_hash, "response": json.loads(prior.response_json)}
                if prior.request_hash != fingerprint or not self.db.evidence_signer.verify("project_mutation", envelope, prior.attestation):
                    raise InvalidStateTransitionError("Idempotency evidence differs.")
                self.permissions.enforce(action, ctx, ctx.organization_id, project_id, session=session)
                return envelope["response"]
            normalized = unicodedata.normalize("NFKD", body.name).encode("ascii", "ignore").decode().lower()
            slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
            if not slug:
                slug = "project-" + hashlib.sha256(body.name.casefold().encode()).hexdigest()[:16]
            duplicate = session.query(ProjectModel).filter_by(organization_id=ctx.organization_id, slug=slug)
            if project_id:
                duplicate = duplicate.filter(ProjectModel.id != project_id)
            if duplicate.first():
                raise DuplicateEntityError("Project name is already in use.")
            if project_id:
                record = session.query(ProjectModel).filter_by(id=project_id, organization_id=ctx.organization_id).with_for_update().populate_existing().first()
                if record is None:
                    raise EntityNotFoundError("Project not available.")
                if record.generation != body.expected_generation:
                    raise InvalidStateTransitionError("Project generation differs.")
                changed = session.execute(update(ProjectModel).where(ProjectModel.id == project_id,
                    ProjectModel.organization_id == ctx.organization_id,
                    ProjectModel.generation == body.expected_generation).values(name=body.name, slug=slug,
                    description=body.description, generation=body.expected_generation + 1))
                if changed.rowcount != 1:
                    raise InvalidStateTransitionError("Concurrent project edit.")
                session.refresh(record)
            else:
                record = ProjectModel(id="proj_" + uuid.uuid4().hex, organization_id=ctx.organization_id,
                    name=body.name, slug=slug, description=body.description, generation=1)
                session.add(record)
                session.flush()
            result = project_view(record)
            envelope = {"organization_id": ctx.organization_id, "project_id": record.id,
                "actor_id": ctx.actor.actor_id, "key": body.idempotency_key,
                "request_hash": fingerprint, "response": result}
            session.add(ProjectMutationModel(id="pm_" + uuid.uuid4().hex, organization_id=ctx.organization_id,
                project_id=record.id, actor_id=ctx.actor.actor_id, idempotency_key=body.idempotency_key,
                request_hash=fingerprint, response_json=encode(result),
                attestation=self.db.evidence_signer.sign("project_mutation", envelope)))
            self.permissions.enforce(action, ctx, ctx.organization_id, project_id, session=session)
            audit_ctx = self.permissions.identity_binder.create_trusted_context(ctx.actor.actor_id,
                ctx.organization_id, record.id, correlation_id=ctx.correlation_id, auth_session_id=ctx.auth_session_id)
            self.audit.record("core.project.updated" if project_id else "core.project.created", audit_ctx,
                record.id, AuditStatus.COMPLETED, {"generation": record.generation}, session=session)
            return result
