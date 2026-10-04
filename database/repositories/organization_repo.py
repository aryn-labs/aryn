"""Repository for Organizations, Projects, and Memberships."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import OrganizationModel, ProjectModel, MembershipModel
from packages.contracts.core import SecurityContext
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    TenantIsolationError,
)


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_organization(self, org_id: str, name: str, slug: str) -> OrganizationModel:
        existing = (
            self.session.query(OrganizationModel)
            .filter((OrganizationModel.id == org_id) | (OrganizationModel.slug == slug))
            .first()
        )
        if existing:
            raise DuplicateEntityError(f"Organization with id '{org_id}' or slug '{slug}' already exists.")

        org = OrganizationModel(id=org_id, name=name, slug=slug)
        self.session.add(org)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(f"Organization with id '{org_id}' or slug '{slug}' already exists.") from exc
        return org

    def get_organization(self, org_id: str) -> OrganizationModel:
        org = self.session.query(OrganizationModel).filter_by(id=org_id).first()
        if not org:
            raise EntityNotFoundError(f"Organization '{org_id}' not found.")
        return org

    def add_member(self, org_id: str, user_id: str, role: str = "operator") -> MembershipModel:
        # Check org exists
        self.get_organization(org_id)
        existing = self.get_member(org_id, user_id)
        if existing:
            raise DuplicateEntityError(f"User '{user_id}' is already a member of organization '{org_id}'.")

        member = MembershipModel(id=f"mem_{org_id}_{user_id}", organization_id=org_id, user_id=user_id, role=role)
        self.session.add(member)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(f"User '{user_id}' is already a member of organization '{org_id}'.") from exc
        return member

    def get_member(self, org_id: str, user_id: str) -> Optional[MembershipModel]:
        return self.session.query(MembershipModel).filter_by(organization_id=org_id, user_id=user_id).first()

    def create_project(self, context: SecurityContext, project_id: str, name: str, slug: str) -> ProjectModel:
        # Enforce tenant isolation: project can only be created in the context's organization
        org = self.get_organization(context.organization_id)
        existing = (
            self.session.query(ProjectModel)
            .filter(
                (ProjectModel.id == project_id)
                | ((ProjectModel.organization_id == org.id) & (ProjectModel.slug == slug))
            )
            .first()
        )
        if existing:
            raise DuplicateEntityError(f"Project with id '{project_id}' or slug '{slug}' already exists in org '{org.id}'.")

        project = ProjectModel(id=project_id, organization_id=org.id, name=name, slug=slug)
        self.session.add(project)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(f"Project with id '{project_id}' or slug '{slug}' already exists in org '{org.id}'.") from exc
        return project

    def get_project(self, context: SecurityContext, project_id: str) -> ProjectModel:
        project = self.session.query(ProjectModel).filter_by(id=project_id).first()
        if not project:
            raise EntityNotFoundError(f"Project '{project_id}' not found.")
        # Tenant boundary check
        if project.organization_id != context.organization_id:
            raise TenantIsolationError(
                f"Tenant boundary violation: Project '{project_id}' belongs to org '{project.organization_id}', "
                f"not context org '{context.organization_id}'."
            )
        return project

    def list_projects(self, context: SecurityContext) -> List[ProjectModel]:
        return self.session.query(ProjectModel).filter_by(organization_id=context.organization_id).all()
