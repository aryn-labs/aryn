"""Agent Factory Service.

Governs the complete lifecycle of autonomous agents:
Blueprint -> Immutable Version -> Bench Safety Evaluation -> Cryptographic Approval -> Publish -> Assignment.
Complies with ARYN-ARCH-001 Section 04 and AGENTS.md rules 3, 4, 5, 6, 7.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from database.connection import DatabaseManager
from database.repositories.agent_repo import AgentRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.audit.logger import AuditLogger
from modules.core.approvals.engine import ApprovalEngine, ApprovalRequiredError
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from modules.bench.runner import BenchRunner
from packages.contracts.core import ActorType, AuditStatus, SecurityContext
from packages.contracts.agent import (
    AgentAssignment,
    AgentBlueprint,
    AgentVersion,
    AgentVersionStatus,
)
from packages.contracts.bench import BenchEvaluationResult, BenchScenario
from packages.contracts.approval import ApprovalRecord
from packages.model_adapters import ModelRouter


class ForbiddenToolError(Exception):
    """Raised when an agent version requests unsafe or unauthorized tools."""
    pass


class UnpublishedVersionError(Exception):
    """Raised when an operation requires a published agent version."""
    pass


class VersionImmutableError(Exception):
    """Raised when an attempt is made to mutate a published agent version."""
    pass


class AgentFactoryService:
    """Authoritative management of Agent Blueprints, Versions, and Assignments."""

    # Risky tools strictly forbidden from agent specification without explicit elevated platform infrastructure
    FORBIDDEN_TOOL_NAMES = frozenset({"terminal", "file", "browser", "code_execution", "bash", "shell", "os_exec"})

    def __init__(
        self,
        db_manager: DatabaseManager,
        bench_runner: BenchRunner,
        approval_engine: Optional[ApprovalEngine] = None,
        permission_engine: Optional[PermissionEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        model_router: Optional[ModelRouter] = None,
    ) -> None:
        self.db_manager = db_manager
        self.bench_runner = bench_runner
        self.audit_logger = audit_logger or AuditLogger(db_manager=db_manager)
        self.approval_engine = approval_engine or ApprovalEngine(db_manager=db_manager, audit_logger=self.audit_logger)
        self.permission_engine = permission_engine or PermissionEngine()
        self.model_router = model_router or ModelRouter()
        self.quality_gate = BenchQualityGate(min_score_threshold=1.0)

    # -------------------------------------------------------------------------
    # 1. Blueprint Management
    # -------------------------------------------------------------------------

    def create_blueprint(
        self,
        context: SecurityContext,
        name: str,
        slug: str,
        description: Optional[str] = None,
    ) -> AgentBlueprint:
        # Check permissions
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)

        blueprint_id = f"abp_{uuid.uuid4().hex[:16]}"
        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            model = repo.create_blueprint(
                context=context,
                blueprint_id=blueprint_id,
                name=name,
                slug=slug,
                description=description,
            )
            bp_contract = AgentBlueprint(
                id=model.id,
                organization_id=model.organization_id,
                project_id=model.project_id,
                name=model.name,
                slug=model.slug,
                description=model.description,
                created_by=model.created_by,
                created_at=model.created_at.isoformat(),
                updated_at=model.updated_at.isoformat(),
            )

        self.audit_logger.record(
            event_type="factory.blueprint.created",
            context=context,
            resource_id=blueprint_id,
            status=AuditStatus.ALLOWED,
            payload={"name": name, "slug": slug},
        )
        return bp_contract

    # -------------------------------------------------------------------------
    # 2. Version Management (Draft creation)
    # -------------------------------------------------------------------------

    def create_version(
        self,
        context: SecurityContext,
        blueprint_id: str,
        version_number: str,
        system_prompt: str,
        model: str,
        tool_grants: Optional[List[str]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentVersion:
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)

        # 1. Model policy validation (ADR-005)
        self.model_router.resolve_model(model)

        # 2. Tool boundary confinement: block forbidden tools
        tools = tool_grants or []
        for t in tools:
            if t.lower() in self.FORBIDDEN_TOOL_NAMES:
                raise ForbiddenToolError(
                    f"Requested tool '{t}' is strictly forbidden by ARYN security policy (AGENTS.md rule 5)."
                )

        version_id = f"av_{uuid.uuid4().hex[:16]}"
        v_temp = AgentVersion(
            id=version_id,
            blueprint_id=blueprint_id,
            version_number=version_number,
            status=AgentVersionStatus.DRAFT,
            system_prompt=system_prompt,
            model=model,
            tool_grants=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata or {},
        )
        payload_hash = v_temp.calculate_payload_hash()

        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            m = repo.create_version(
                context=context,
                version_id=version_id,
                blueprint_id=blueprint_id,
                version_number=version_number,
                system_prompt=system_prompt,
                model=model,
                tool_grants=tools,
                payload_hash=payload_hash,
                temperature=temperature,
                max_tokens=max_tokens,
                metadata=metadata,
            )
            created_version = AgentVersion(
                id=m.id,
                blueprint_id=m.blueprint_id,
                version_number=m.version_number,
                status=AgentVersionStatus(m.status),
                system_prompt=m.system_prompt,
                model=m.model,
                tool_grants=json.loads(m.tool_grants_json),
                temperature=m.temperature,
                max_tokens=m.max_tokens,
                metadata=json.loads(m.metadata_json),
                payload_hash=m.payload_hash,
                created_at=m.created_at.isoformat(),
            )

        self.audit_logger.record(
            event_type="factory.version.created",
            context=context,
            resource_id=version_id,
            status=AuditStatus.ALLOWED,
            payload={
                "blueprint_id": blueprint_id,
                "version_number": version_number,
                "payload_hash": payload_hash,
                "model": model,
            },
        )
        return created_version

    # -------------------------------------------------------------------------
    # 3. Bench Evaluation Integration
    # -------------------------------------------------------------------------

    async def evaluate_version_with_bench(
        self,
        context: SecurityContext,
        version_id: str,
        scenarios: Optional[List[BenchScenario]] = None,
    ) -> BenchEvaluationResult:
        # Retrieve version
        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            m = repo.get_version(context, version_id)
            version_contract = AgentVersion(
                id=m.id,
                blueprint_id=m.blueprint_id,
                version_number=m.version_number,
                status=AgentVersionStatus(m.status),
                system_prompt=m.system_prompt,
                model=m.model,
                tool_grants=json.loads(m.tool_grants_json),
                temperature=m.temperature,
                max_tokens=m.max_tokens,
                metadata=json.loads(m.metadata_json),
                payload_hash=m.payload_hash,
                created_at=m.created_at.isoformat(),
            )
            # Mark version as evaluating
            repo.update_version_status(context, version_id, "evaluating")

        # Execute isolated bench evaluation
        result = await self.bench_runner.evaluate_agent_version(context, version_contract, scenarios)

        # Store evaluation and update version status
        with self.db_manager.session() as session:
            bench_repo = BenchRepository(session)
            agent_repo = AgentRepository(session)
            bench_repo.record_evaluation(context, result)

            if result.passed:
                agent_repo.update_version_status(context, version_id, "draft", evaluation_id=result.evaluation_id)
            else:
                agent_repo.update_version_status(context, version_id, "rejected", evaluation_id=result.evaluation_id)

        self.audit_logger.record(
            event_type="bench.evaluation.completed",
            context=context,
            resource_id=version_id,
            status=AuditStatus.COMPLETED if result.passed else AuditStatus.FAILED,
            payload={
                "evaluation_id": result.evaluation_id,
                "passed": result.passed,
                "score": result.score,
                "passed_scenarios": result.passed_scenarios,
                "total_scenarios": result.total_scenarios,
            },
        )
        return result

    # -------------------------------------------------------------------------
    # 4. Cryptographic Approval
    # -------------------------------------------------------------------------

    def approve_version(
        self,
        context: SecurityContext,
        version_id: str,
        comments: Optional[str] = None,
    ) -> ApprovalRecord:
        """Enforces that an agent version passes Bench quality gate before human approval is granted."""
        # 1. Enforce that agent cannot approve itself
        if context.actor.actor_type == ActorType.AGENT:
            raise PermissionDeniedError("Agents cannot grant approvals or self-publish.")

        # 2. Check latest passing evaluation
        with self.db_manager.session() as session:
            bench_repo = BenchRepository(session)
            agent_repo = AgentRepository(session)
            m = agent_repo.get_version(context, version_id)

            passing_eval = bench_repo.get_latest_passing_evaluation(context, version_id)
            if not passing_eval:
                raise QualityGateFailedError(
                    f"Agent version '{version_id}' cannot be approved: no passing Bench evaluation found."
                )

            payload_hash = m.payload_hash

        # 3. Delegate to ApprovalEngine (enforces admin role and exact payload hash binding)
        record = self.approval_engine.grant_approval(
            context=context,
            target_type="agent_version",
            target_id=version_id,
            payload_hash=payload_hash,
            comments=comments,
        )

        # 4. Transition version to approved
        with self.db_manager.session() as session:
            agent_repo = AgentRepository(session)
            agent_repo.update_version_status(context, version_id, "approved")

        self.audit_logger.record(
            event_type="factory.version.approved",
            context=context,
            resource_id=version_id,
            status=AuditStatus.ALLOWED,
            payload={"approval_id": record.approval_id, "payload_hash": payload_hash},
        )
        return record

    # -------------------------------------------------------------------------
    # 5. Publication (Making version immutable)
    # -------------------------------------------------------------------------

    def publish_version(
        self,
        context: SecurityContext,
        version_id: str,
    ) -> AgentVersion:
        """Promotes an approved version to 'published', making it permanently immutable."""
        # 1. Ensure actor is human with admin or operator role (agents CANNOT publish)
        if context.actor.actor_type == ActorType.AGENT:
            raise PermissionDeniedError("Agents cannot publish versions.")

        with self.db_manager.session() as session:
            agent_repo = AgentRepository(session)
            bench_repo = BenchRepository(session)
            m = agent_repo.get_version(context, version_id)

            # 2. Quality gate check
            passing_eval = bench_repo.get_latest_passing_evaluation(context, version_id)
            if not passing_eval:
                raise QualityGateFailedError(
                    f"Cannot publish agent version '{version_id}': no passing Bench evaluation found."
                )

            # 3. Cryptographic approval check (matches exact payload hash)
            self.approval_engine.verify_approval(
                context=context,
                target_type="agent_version",
                target_id=version_id,
                expected_payload_hash=m.payload_hash,
            )

            # 4. Transition to published
            published_model = agent_repo.update_version_status(
                context=context,
                version_id=version_id,
                target_status="published",
                published_by=context.actor.actor_id,
            )

            published_version = AgentVersion(
                id=published_model.id,
                blueprint_id=published_model.blueprint_id,
                version_number=published_model.version_number,
                status=AgentVersionStatus.PUBLISHED,
                system_prompt=published_model.system_prompt,
                model=published_model.model,
                tool_grants=json.loads(published_model.tool_grants_json),
                temperature=published_model.temperature,
                max_tokens=published_model.max_tokens,
                metadata=json.loads(published_model.metadata_json),
                payload_hash=published_model.payload_hash,
                evaluation_id=published_model.evaluation_id,
                published_at=published_model.published_at.isoformat() if published_model.published_at else None,
                published_by=published_model.published_by,
                created_at=published_model.created_at.isoformat(),
            )

        self.audit_logger.record(
            event_type="factory.version.published",
            context=context,
            resource_id=version_id,
            status=AuditStatus.COMPLETED,
            payload={
                "blueprint_id": published_version.blueprint_id,
                "version_number": published_version.version_number,
                "published_by": context.actor.actor_id,
                "payload_hash": published_version.payload_hash,
            },
        )
        return published_version

    # -------------------------------------------------------------------------
    # 6. Operational Assignment
    # -------------------------------------------------------------------------

    def assign_agent(
        self,
        context: SecurityContext,
        blueprint_id: str,
        version_id: str,
        role_name: str,
        division_id: Optional[str] = None,
    ) -> AgentAssignment:
        """Assigns a published agent version to a project/division."""
        assignment_id = f"asgn_{uuid.uuid4().hex[:16]}"
        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            m = repo.create_assignment(
                context=context,
                assignment_id=assignment_id,
                blueprint_id=blueprint_id,
                version_id=version_id,
                role_name=role_name,
                division_id=division_id,
            )
            assignment = AgentAssignment(
                id=m.id,
                organization_id=m.organization_id,
                project_id=m.project_id,
                division_id=m.division_id,
                blueprint_id=m.blueprint_id,
                version_id=m.version_id,
                role_name=m.role_name,
                status=m.status,
                created_at=m.created_at.isoformat(),
                updated_at=m.updated_at.isoformat(),
            )

        self.audit_logger.record(
            event_type="factory.agent.assigned",
            context=context,
            resource_id=assignment_id,
            status=AuditStatus.ALLOWED,
            payload={
                "blueprint_id": blueprint_id,
                "version_id": version_id,
                "role_name": role_name,
                "division_id": division_id,
            },
        )
        return assignment

    def get_assignment(self, context: SecurityContext, assignment_id: str) -> AgentAssignment:
        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            m = repo.get_assignment(context, assignment_id)
            return AgentAssignment(
                id=m.id,
                organization_id=m.organization_id,
                project_id=m.project_id,
                division_id=m.division_id,
                blueprint_id=m.blueprint_id,
                version_id=m.version_id,
                role_name=m.role_name,
                status=m.status,
                created_at=m.created_at.isoformat(),
                updated_at=m.updated_at.isoformat(),
            )
