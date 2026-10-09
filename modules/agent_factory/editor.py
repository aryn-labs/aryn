"""Generation guarded editing; candidate creation delegates to existing Factory authority."""
import json

from database.repositories.agent_repo import AgentRepository
from database.repositories.exceptions import EntityNotFoundError, InvalidStateTransitionError
from database.schema import AgentBlueprintModel, AgentEditorLayoutModel, AgentWorkingCopyModel
from packages.contracts.agent import AgentVersion
from packages.contracts.agent_builder import WorkingCopyView, LayoutView, Viewport
from packages.contracts.core import AuditStatus


class EditorConflictError(InvalidStateTransitionError):
    """A scoped generation differs from the writer's expected generation."""


class AgentEditor:
    def __init__(self, factory):
        self.factory = factory
        self.db = factory.db_manager
        self.permissions = factory.permission_engine

    def authorize(self, session, context, blueprint_id, write=False):
        self.permissions.enforce("version:create" if write else "run:read", context,
            context.organization_id, context.project_id, session=session)
        query = session.query(AgentBlueprintModel).filter_by(id=blueprint_id,
            organization_id=context.organization_id, project_id=context.project_id)
        if write:
            query = query.with_for_update().populate_existing()
        if query.first() is None:
            raise EntityNotFoundError("Blueprint unavailable in this scope.")

    def copy(self, session, context, blueprint_id):
        return session.query(AgentWorkingCopyModel).filter_by(blueprint_id=blueprint_id,
            organization_id=context.organization_id, project_id=context.project_id).with_for_update().populate_existing().first()

    def view(self, context, blueprint_id, record):
        return WorkingCopyView(organization_id=context.organization_id, project_id=context.project_id,
            blueprint_id=blueprint_id, generation=record.generation if record else 0,
            definition=json.loads(record.definition_json) if record and record.definition_json else None,
            source_version_id=record.source_version_id if record else None,
            updated_at=record.updated_at.isoformat() if record else None)

    def read(self, context, blueprint_id):
        with self.db.session() as session:
            self.authorize(session, context, blueprint_id)
            record = session.query(AgentWorkingCopyModel).filter_by(blueprint_id=blueprint_id,
                organization_id=context.organization_id, project_id=context.project_id).first()
            result = self.view(context, blueprint_id, record)
            self.authorize(session, context, blueprint_id)
            return result

    def save(self, context, blueprint_id, body):
        with self.db.session(write=True) as session:
            self.authorize(session, context, blueprint_id, True)
            record = self.copy(session, context, blueprint_id)
            if body.expected_generation != (record.generation if record else 0):
                raise EditorConflictError("Working copy changed; reload or restore your unsaved input explicitly.")
            if body.source_version_id:
                version = AgentRepository(session).get_version(context, body.source_version_id)
                if version.blueprint_id != blueprint_id:
                    raise EntityNotFoundError("Source version unavailable for this blueprint.")
                AgentVersion.from_stored(version).verify_integrity(require_canonical=True)
            if not record:
                record = AgentWorkingCopyModel(blueprint_id=blueprint_id, organization_id=context.organization_id,
                    project_id=context.project_id, generation=0)
                session.add(record)
            record.generation += 1
            record.definition_json = body.definition.model_dump_json()
            record.source_version_id = body.source_version_id
            record.updated_by = context.actor.actor_id
            session.flush()
            self.authorize(session, context, blueprint_id, True)
            self.factory.audit_logger.record("factory.working_copy.saved", context, blueprint_id, AuditStatus.COMPLETED,
                {"generation": record.generation}, session=session)
            return self.view(context, blueprint_id, record)

    def discard(self, context, blueprint_id, body):
        with self.db.session(write=True) as session:
            self.authorize(session, context, blueprint_id, True)
            record = self.copy(session, context, blueprint_id)
            self.check_generation(record, body)
            record.definition_json = None
            record.source_version_id = None
            record.generation += 1
            record.updated_by = context.actor.actor_id
            self.authorize(session, context, blueprint_id, True)
            self.factory.audit_logger.record("factory.working_copy.discarded", context, blueprint_id, AuditStatus.COMPLETED,
                {"generation": record.generation}, session=session)
            return self.view(context, blueprint_id, record)

    def check_generation(self, record, body):
        if not record or record.generation != body.expected_generation:
            raise EditorConflictError("Working copy generation changed; reload before this action.")

    def candidate(self, context, blueprint_id, body):
        with self.db.session(write=True) as session:
            self.authorize(session, context, blueprint_id, True)
            record = self.copy(session, context, blueprint_id)
            self.check_generation(record, body)
            if not record.definition_json:
                raise InvalidStateTransitionError("Save a working copy before creating a candidate.")
            from packages.contracts.agent_builder import AgentDraft
            definition = AgentDraft.model_validate_json(record.definition_json)
            result = self.factory.create_version(context, blueprint_id=blueprint_id,
                **definition.model_dump(mode="json"), session=session)
            self.authorize(session, context, blueprint_id, True)
            return result

    def layout(self, context, blueprint_id, body=None):
        with self.db.session(write=body is not None) as session:
            self.authorize(session, context, blueprint_id, body is not None)
            query = session.query(AgentEditorLayoutModel).filter_by(blueprint_id=blueprint_id,
                actor_id=context.actor.actor_id, organization_id=context.organization_id, project_id=context.project_id)
            record = query.with_for_update().populate_existing().first() if body else query.first()
            if body:
                if body.expected_generation != (record.generation if record else 0):
                    raise EditorConflictError("Layout generation changed; reload before saving.")
                if not record:
                    record = AgentEditorLayoutModel(blueprint_id=blueprint_id, actor_id=context.actor.actor_id,
                        organization_id=context.organization_id, project_id=context.project_id, generation=0)
                    session.add(record)
                record.generation += 1
                record.layout_json = json.dumps(body.model_dump(mode="json", exclude={"expected_generation"}))
                session.flush()
                self.authorize(session, context, blueprint_id, True)
            return LayoutView(generation=record.generation if record else 0,
                **(json.loads(record.layout_json) if record else {"positions": [], "viewport": Viewport()}))
