"""Repository for Agent Blueprints, Immutable Versions, and Assignments.

Enforces tenant scoping, strict immutability for published versions, and assignment invariants.
Complies with ARYN-ARCH-001 Section 04 and AGENTS.md rules 3, 4, 7.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import AgentBlueprintModel, AgentVersionModel, AgentAssignmentModel, utc_now
from packages.contracts.core import SecurityContext
from packages.contracts.agent import (
    AgentBudgetPolicy,
    AgentConstraints,
    AgentEvaluationReference,
    AgentModelPolicy,
    AgentOutputContract,
    AgentToolPolicy,
    AgentVersion,
)
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    TenantIsolationError,
)


class AgentRepository:
    """Manages persistent blueprints, versions, and assignments with tenant isolation."""

    VALID_VERSION_TRANSITIONS = {
        "draft": {"evaluating", "approved", "rejected"},
        "evaluating": {"draft", "rejected"},
        "approved": {"published", "draft", "evaluating", "rejected"},
        "published": {"deprecated"},
        "deprecated": set(),
        "rejected": {"draft", "evaluating"},
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    # -------------------------------------------------------------
    # Blueprint Operations
    # -------------------------------------------------------------

    def create_blueprint(
        self,
        context: SecurityContext,
        blueprint_id: str,
        name: str,
        slug: str,
        description: Optional[str] = None,
        role: Optional[str] = None,
        objective: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> AgentBlueprintModel:
        existing = (
            self.session.query(AgentBlueprintModel)
            .filter_by(project_id=context.project_id, slug=slug)
            .first()
        )
        if existing:
            raise DuplicateEntityError(
                f"Agent blueprint with slug '{slug}' already exists in project '{context.project_id}'."
            )

        blueprint = AgentBlueprintModel(
            id=blueprint_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            name=name,
            slug=slug,
            description=description,
            role=role,
            objective=objective,
            owner=owner,
            created_by=context.actor.actor_id,
        )
        self.session.add(blueprint)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Agent blueprint '{blueprint_id}' or slug '{slug}' conflict in project '{context.project_id}'."
            ) from exc
        return blueprint

    def get_blueprint(self, context: SecurityContext, blueprint_id: str) -> AgentBlueprintModel:
        blueprint = self.session.query(AgentBlueprintModel).filter_by(id=blueprint_id).first()
        if not blueprint:
            raise EntityNotFoundError(f"Agent blueprint '{blueprint_id}' not found.")
        if blueprint.organization_id != context.organization_id or blueprint.project_id != context.project_id:
            raise TenantIsolationError(
                f"Tenant boundary violation: Blueprint '{blueprint_id}' belongs to org/project "
                f"'{blueprint.organization_id}/{blueprint.project_id}', not context '{context.organization_id}/{context.project_id}'."
            )
        return blueprint

    def list_blueprints(self, context: SecurityContext) -> List[AgentBlueprintModel]:
        return (
            self.session.query(AgentBlueprintModel)
            .filter_by(organization_id=context.organization_id, project_id=context.project_id)
            .order_by(AgentBlueprintModel.created_at.desc())
            .all()
        )

    # -------------------------------------------------------------
    # Version Operations
    # -------------------------------------------------------------

    def create_version(
        self,
        context: SecurityContext,
        version_id: str,
        blueprint_id: str,
        version_number: str,
        system_prompt: str,
        model: str,
        tool_grants: List[str],
        payload_hash: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        metadata: Optional[Dict[str, Any]] = None,
        schema_version: str = "1.0.0",
        role: Optional[str] = None,
        objective: Optional[str] = None,
        owner: Optional[str] = None,
        output_contract: Optional[Dict[str, Any] | AgentOutputContract] = None,
        constraints: Optional[Dict[str, Any] | List[str] | AgentConstraints] = None,
        tool_policy: Optional[Dict[str, Any] | AgentToolPolicy] = None,
        model_policy: Optional[Dict[str, Any] | AgentModelPolicy] = None,
        budget_policy: Optional[Dict[str, Any] | AgentBudgetPolicy] = None,
        evaluation_reference: Optional[Dict[str, Any] | AgentEvaluationReference] = None,
    ) -> AgentVersionModel:
        # Validate parent blueprint belongs to context
        blueprint = self.get_blueprint(context, blueprint_id)

        existing = (
            self.session.query(AgentVersionModel)
            .filter_by(blueprint_id=blueprint.id, version_number=version_number)
            .first()
        )
        if existing:
            raise DuplicateEntityError(
                f"Agent version '{version_number}' already exists for blueprint '{blueprint_id}'."
            )

        resolved_role = role or blueprint.role or "general_agent"
        resolved_objective = objective or blueprint.objective or ""
        resolved_owner = owner or blueprint.owner

        # Validate caller-supplied hash against the exact data about to be stored.
        contract = AgentVersion(
            id=version_id,
            blueprint_id=blueprint.id,
            version_number=version_number,
            system_prompt=system_prompt,
            model=model,
            tool_grants=tool_grants,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata or {},
            payload_hash=payload_hash,
            schema_version=schema_version,
            role=resolved_role,
            objective=resolved_objective,
            owner=resolved_owner,
            output_contract=output_contract or AgentOutputContract(),
            constraints=constraints or AgentConstraints(),
            tool_policy=tool_policy or AgentToolPolicy(tool_grants=tool_grants),
            model_policy=model_policy or AgentModelPolicy(primary_model=model, temperature=temperature, max_tokens=max_tokens),
            budget_policy=budget_policy or AgentBudgetPolicy(),
            evaluation_reference=evaluation_reference or AgentEvaluationReference(),
        )
        contract.verify_integrity()

        version = AgentVersionModel(
            id=version_id,
            blueprint_id=blueprint.id,
            version_number=version_number,
            status="draft",
            system_prompt=system_prompt,
            model=model,
            tool_grants_json=json.dumps(sorted(tool_grants)),
            temperature=temperature,
            max_tokens=max_tokens,
            metadata_json=json.dumps(metadata or {}),
            payload_hash=payload_hash,
            schema_version=contract.schema_version,
            role=contract.role,
            objective=contract.objective,
            owner=contract.owner,
            output_contract_json=json.dumps(contract.output_contract.model_dump(mode="json")),
            constraints_json=json.dumps(contract.constraints.model_dump(mode="json")),
            tool_policy_json=json.dumps(contract.tool_policy.model_dump(mode="json")),
            model_policy_json=json.dumps(contract.model_policy.model_dump(mode="json")),
            budget_policy_json=json.dumps(contract.budget_policy.model_dump(mode="json")),
            evaluation_reference_json=json.dumps(contract.evaluation_reference.model_dump(mode="json")),
        )
        self.session.add(version)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Version '{version_number}' for blueprint '{blueprint_id}' already exists."
            ) from exc
        return version

    def get_version(self, context: SecurityContext, version_id: str, for_update: bool = False) -> AgentVersionModel:
        query = self.session.query(AgentVersionModel).filter_by(id=version_id)
        if for_update:
            query = query.with_for_update()
        version = query.first()
        if not version:
            raise EntityNotFoundError(f"Agent version '{version_id}' not found.")
        # Tenant boundary check via parent blueprint
        self.get_blueprint(context, version.blueprint_id)
        AgentVersion.from_stored(version)
        return version

    def update_version_status(
        self,
        context: SecurityContext,
        version_id: str,
        target_status: str,
        published_by: Optional[str] = None,
        evaluation_id: Optional[str] = None,
    ) -> AgentVersionModel:
        version = self.get_version(context, version_id, for_update=True)
        current = version.status.lower()
        target = target_status.lower()

        if current == target:
            return version

        # Published versions are strictly IMMUTABLE
        if current == "published" and target != "deprecated":
            raise InvalidStateTransitionError(
                f"Published agent version '{version_id}' is immutable and cannot transition to '{target}'. "
                "Only 'deprecated' is permitted."
            )

        allowed = self.VALID_VERSION_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal version status transition from '{current}' to '{target}'. Allowed: {sorted(allowed)}."
            )

        version.status = target
        if target == "evaluating":
            version.evaluation_id = None
        if evaluation_id:
            version.evaluation_id = evaluation_id

        if target == "published":
            version.published_at = utc_now()
            version.published_by = published_by or context.actor.actor_id

        self.session.flush()
        return version

    # -------------------------------------------------------------
    # Assignment Operations
    # -------------------------------------------------------------

    def create_assignment(
        self,
        context: SecurityContext,
        assignment_id: str,
        blueprint_id: str,
        version_id: str,
        role_name: str,
        division_id: Optional[str] = None,
    ) -> AgentAssignmentModel:
        # Validate blueprint and version in tenant
        blueprint = self.get_blueprint(context, blueprint_id)
        version = self.get_version(context, version_id)

        if version.blueprint_id != blueprint.id:
            raise InvalidStateTransitionError("Assignment blueprint must match the version's parent blueprint.")

        # Invariant: Version MUST be published before it can be assigned
        if version.status != "published":
            raise InvalidStateTransitionError(
                f"Cannot assign agent version '{version_id}' with status '{version.status}'. "
                "Only 'published' versions can be assigned to projects or divisions."
            )

        existing = (
            self.session.query(AgentAssignmentModel)
            .filter_by(project_id=context.project_id, role_name=role_name)
            .first()
        )
        if existing:
            raise DuplicateEntityError(
                f"Agent assignment with role '{role_name}' already exists in project '{context.project_id}'."
            )

        assignment = AgentAssignmentModel(
            id=assignment_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            division_id=division_id,
            blueprint_id=blueprint.id,
            version_id=version.id,
            role_name=role_name,
            status="active",
        )
        self.session.add(assignment)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Assignment conflict for role '{role_name}' in project '{context.project_id}'."
            ) from exc
        return assignment

    def get_assignment(self, context: SecurityContext, assignment_id: str) -> AgentAssignmentModel:
        assignment = self.session.query(AgentAssignmentModel).filter_by(id=assignment_id).first()
        if not assignment:
            raise EntityNotFoundError(f"Agent assignment '{assignment_id}' not found.")
        if assignment.organization_id != context.organization_id or assignment.project_id != context.project_id:
            raise TenantIsolationError(
                f"Tenant boundary violation: Assignment '{assignment_id}' belongs to org/project "
                f"'{assignment.organization_id}/{assignment.project_id}', not context '{context.organization_id}/{context.project_id}'."
            )
        return assignment

    def list_assignments(self, context: SecurityContext) -> List[AgentAssignmentModel]:
        return (
            self.session.query(AgentAssignmentModel)
            .filter_by(organization_id=context.organization_id, project_id=context.project_id)
            .order_by(AgentAssignmentModel.created_at.desc())
            .all()
        )
