"""Project-owned divisions; existing Core is the only mutation authority."""
import uuid

from database.repositories.exceptions import EntityNotFoundError, InvalidStateTransitionError
from database.schema import DivisionModel
from modules.core.audit.logger import AuditLogger
from packages.contracts.core import AuditStatus


class WorkspaceService:
    def __init__(self, db, permissions):
        self.db = db
        self.permissions = permissions
        self.audit = AuditLogger(db_manager=db)

    def save_division(self, context, body, division_id=None):
        with self.db.session(write=True) as session:
            self.permissions.enforce("division:manage", context, context.organization_id, context.project_id, session=session)
            if division_id:
                division = session.query(DivisionModel).filter_by(id=division_id,
                    organization_id=context.organization_id, project_id=context.project_id).with_for_update().populate_existing().first()
                if division is None:
                    raise EntityNotFoundError("Division unavailable in this project.")
                if division.generation != body.expected_generation:
                    raise InvalidStateTransitionError("Division generation changed; reload before saving.")
                division.generation += 1
            else:
                division = DivisionModel(id="div_" + uuid.uuid4().hex,
                    organization_id=context.organization_id, project_id=context.project_id, generation=1)
                session.add(division)
            for key, value in body.model_dump(exclude={"expected_generation"}).items():
                setattr(division, key, value)
            session.flush()
            self.permissions.enforce("division:manage", context, context.organization_id, context.project_id, session=session)
            self.audit.record("core.division.updated" if division_id else "core.division.created", context,
                division.id, AuditStatus.COMPLETED, {"generation": division.generation}, session=session)
            return {"id": division.id, "organization_id": division.organization_id,
                "project_id": division.project_id, "name": division.name, "slug": division.slug,
                "description": division.description, "generation": division.generation}
