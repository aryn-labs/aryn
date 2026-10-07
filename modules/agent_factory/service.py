"""Agent Factory Service.

Governs the complete lifecycle of autonomous agents:
Blueprint -> Immutable Version -> Bench Safety Evaluation -> Cryptographic Approval -> Publish -> Assignment.
Complies with ARYN-ARCH-001 Section 04 and AGENTS.md rules 3, 4, 5, 6, 7.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Dict, List, Optional

from database.connection import DatabaseManager
from database.repositories.agent_repo import AgentRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.audit.logger import AuditLogger
from modules.core.approvals.engine import ApprovalEngine, ApprovalRequiredError
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from modules.bench.regression import audit_regression_denial
from modules.bench.runner import BenchRunner
from packages.contracts.core import ActorType, AuditStatus, SecurityContext
from packages.contracts.agent import (
    AgentAssignment,
    AgentBlueprint,
    AgentBudgetPolicy,
    AgentConstraints,
    AgentDefinition,
    AgentEvaluationReference,
    AgentModelPolicy,
    AgentOutputContract,
    AgentToolPolicy,
    AgentVersion,
    AgentVersionStatus,
    ForbiddenToolError,
    VersionIntegrityError,
)
from packages.contracts.bench import BenchEvaluationResult, BenchScenario
from packages.contracts.approval import ApprovalRecord
from packages.model_adapters import ModelRouter


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
        self.permission_engine = permission_engine or PermissionEngine(db_manager=db_manager)
        self.approval_engine = approval_engine or ApprovalEngine(
            db_manager=db_manager,
            audit_logger=self.audit_logger,
            permission_engine=self.permission_engine,
        )
        self.model_router = model_router or ModelRouter()
        self.quality_gate = BenchQualityGate(min_score_threshold=1.0)
        self.bench_runner.evidence_signer = db_manager.evidence_signer
        self.bench_runner.approval_authority = self.approval_engine

    # -------------------------------------------------------------------------
    # 1. Blueprint Management
    # -------------------------------------------------------------------------

    def create_blueprint(
        self,
        context: SecurityContext,
        name: str,
        slug: str,
        description: Optional[str] = None,
        role: Optional[str] = None,
        objective: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> AgentBlueprint:
        # Check permissions
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)

        blueprint_id = f"abp_{uuid.uuid4().hex[:16]}"
        with self.db_manager.session(write=True) as session:
            repo = AgentRepository(session)
            model = repo.create_blueprint(
                context=context,
                blueprint_id=blueprint_id,
                name=name,
                slug=slug,
                description=description,
                role=role,
                objective=objective,
                owner=owner,
            )
            bp_contract = AgentBlueprint.from_stored(model)

        self.audit_logger.record(
            event_type="factory.blueprint.created",
            context=context,
            resource_id=blueprint_id,
            status=AuditStatus.ALLOWED,
            payload={"name": name, "slug": slug, "role": role, "owner": owner or context.actor.actor_id},
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
    ) -> AgentVersion:
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)

        # 1. Model policy validation (ADR-005)
        self.model_router.resolve_model(model)
        if model_policy:
            parsed_model_policy = (
                AgentModelPolicy.model_validate(model_policy)
                if isinstance(model_policy, dict)
                else model_policy
            )
            parsed_model_policy.validate_model(model)

        # 2. Tool boundary confinement: explicit grants & deny-by-default
        if tool_policy:
            parsed_tool_policy = (
                AgentToolPolicy.model_validate(tool_policy)
                if isinstance(tool_policy, dict)
                else tool_policy
            )
            parsed_tool_policy.validate_tool_grants()
            tools = parsed_tool_policy.tool_grants
        else:
            tools = tool_grants or []

        for t in tools:
            if t.lower() in self.FORBIDDEN_TOOL_NAMES:
                raise ForbiddenToolError(
                    f"Requested tool '{t}' is strictly forbidden by ARYN security policy (AGENTS.md rule 5)."
                )

        # 3. Evaluation reference validation
        if evaluation_reference:
            parsed_eval_ref = (
                AgentEvaluationReference.model_validate(evaluation_reference)
                if isinstance(evaluation_reference, dict)
                else AgentEvaluationReference.model_validate(evaluation_reference.model_dump())
            )
            evaluation_reference = parsed_eval_ref

        version_id = f"av_{uuid.uuid4().hex[:16]}"

        with self.db_manager.session(write=True) as session:
            repo = AgentRepository(session)
            blueprint = repo.get_blueprint(context, blueprint_id)

            resolved_role = role or blueprint.role or "general_agent"
            resolved_objective = objective or blueprint.objective or ""
            resolved_owner = owner or blueprint.owner or context.actor.actor_id

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
                schema_version=schema_version,
                role=resolved_role,
                objective=resolved_objective,
                owner=resolved_owner,
                output_contract=output_contract or AgentOutputContract(),
                constraints=constraints or AgentConstraints(),
                tool_policy=tool_policy or AgentToolPolicy(tool_grants=tools),
                model_policy=model_policy or AgentModelPolicy(primary_model=model, temperature=temperature, max_tokens=max_tokens),
                budget_policy=budget_policy or AgentBudgetPolicy(),
                evaluation_reference=evaluation_reference or AgentEvaluationReference(),
            )
            payload_hash = v_temp.calculate_payload_hash()

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
                schema_version=schema_version,
                role=resolved_role,
                objective=resolved_objective,
                owner=resolved_owner,
                output_contract=output_contract,
                constraints=constraints,
                tool_policy=tool_policy,
                model_policy=model_policy,
                budget_policy=budget_policy,
                evaluation_reference=evaluation_reference,
            )
            created_version = AgentVersion.from_stored(m)

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
                "schema_version": schema_version,
                "role": resolved_role,
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
        on_event: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> BenchEvaluationResult:
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        # Retrieve version
        with self.db_manager.session(write=True) as session:
            repo = AgentRepository(session)
            m = repo.get_version(context, version_id, for_update=True)
            version_contract = AgentVersion.from_stored(m)
            if version_contract.canonical_format != 3:
                raise QualityGateFailedError(
                    f"Agent version '{version_id}' uses legacy payload format (format {version_contract.canonical_format}). "
                    "Legacy versions cannot enter Bench evaluation; create a new version."
                )
            if m.status not in {"draft", "rejected", "approved"}:
                raise InvalidStateTransitionError("Bench evaluation is already active or version is immutable.")
            self.bench_runner.resolve_suite(version_contract, scenarios)
            # Mark version as evaluating
            repo.update_version_status(context, version_id, "evaluating")

        # Execute isolated bench evaluation
        self.bench_runner.evidence_signer = self.db_manager.evidence_signer
        try:
            result = await self.bench_runner.evaluate_agent_version(context, version_contract, scenarios, on_event=on_event)
        except BaseException:
            with self.db_manager.session(write=True) as session:
                AgentRepository(session).update_version_status(context, version_id, "rejected")
            raise

        # Store evaluation and update version status
        with self.db_manager.session(write=True) as session:
            bench_repo = BenchRepository(session, self.db_manager.evidence_signer)
            agent_repo = AgentRepository(session)
            current = agent_repo.get_version(context, version_id, for_update=True)
            if current.status != "evaluating" or current.payload_hash != result.payload_hash:
                raise InvalidStateTransitionError("Evaluation no longer owns the current version state.")
            bench_repo.record_evaluation(context, result)

            if result.passed:
                agent_repo.update_version_status(context, version_id, "draft", evaluation_id=result.evaluation_id)
            else:
                agent_repo.update_version_status(context, version_id, "rejected", evaluation_id=result.evaluation_id)
            from database.repositories.bench_regression_repo import BenchRegressionRepository
            BenchRegressionRepository(session, self.db_manager.evidence_signer).compare(
                context, version_id, persist=True)

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

    @audit_regression_denial
    def approve_version(
        self,
        context: SecurityContext,
        version_id: str,
        comments: Optional[str] = None,
        expected_payload_hash: Optional[str] = None,
    ) -> ApprovalRecord:
        """Approve current attested Bench evidence and transition atomically."""
        if context.actor.actor_type == ActorType.AGENT:
            raise PermissionDeniedError("Agents cannot grant approvals or self-publish.")
        with self.db_manager.session(write=True) as session:
            agent_repo = AgentRepository(session)
            version = agent_repo.get_version(context, version_id, for_update=True)
            if expected_payload_hash is not None and version.payload_hash != expected_payload_hash:
                from modules.core.approvals.engine import PayloadHashMismatchError
                raise PayloadHashMismatchError("Browser review differs from current canonical payload.")
            version_contract = AgentVersion.from_stored(version)
            if version_contract.canonical_format != 3:
                raise QualityGateFailedError(
                    f"Agent version '{version_id}' uses legacy payload format (format {version_contract.canonical_format}). "
                    "Legacy versions cannot be approved; create a new version."
                )
            passing_eval = BenchRepository(session, self.db_manager.evidence_signer).get_latest_passing_evaluation(context, version_id)
            if not passing_eval:
                raise QualityGateFailedError(f"Agent version '{version_id}' cannot be approved: no passing Bench evaluation found.")
            record = self.approval_engine.grant_approval(
                context, "agent_version", version_id, version.payload_hash, comments, session=session)
            agent_repo.update_version_status(context, version_id, "approved")
            self.audit_logger.record("factory.version.approved", context, version_id, AuditStatus.ALLOWED,
                                     {"approval_id": record.approval_id, "payload_hash": version.payload_hash,
                                      "evaluation_id": passing_eval.id}, session=session)
        return record

    # -------------------------------------------------------------------------
    # 5. Publication (Making version immutable)
    # -------------------------------------------------------------------------

    @audit_regression_denial
    def publish_version(
        self,
        context: SecurityContext,
        version_id: str,
    ) -> AgentVersion:
        """Promotes an approved version to 'published', making it permanently immutable."""
        # 1. Ensure actor is human with admin or operator role (agents CANNOT publish)
        if context.actor.actor_type == ActorType.AGENT:
            raise PermissionDeniedError("Agents cannot publish versions.")

        self.permission_engine.enforce("version:publish", context, context.organization_id, context.project_id)

        with self.db_manager.session(write=True) as session:
            agent_repo = AgentRepository(session)
            bench_repo = BenchRepository(session, self.db_manager.evidence_signer)
            m = agent_repo.get_version(context, version_id, for_update=True)
            version_contract = AgentVersion.from_stored(m)
            if version_contract.canonical_format != 3:
                raise InvalidStateTransitionError(
                    f"Cannot publish agent version '{version_id}': version uses legacy payload format (format {version_contract.canonical_format}). "
                    "Publication requires current canonical payload format (format 3); create a new version."
                )

            # 2. Quality gate check
            passing_eval = bench_repo.get_latest_passing_evaluation(context, version_id)
            if not passing_eval:
                raise QualityGateFailedError(
                    f"Cannot publish agent version '{version_id}': no passing Bench evaluation found."
                )

            # 3. Cryptographic approval check (matches exact payload hash)
            approval = self.approval_engine.verify_approval(
                context=context,
                target_type="agent_version",
                target_id=version_id,
                expected_payload_hash=m.payload_hash,
                session=session,
            )
            if m.status not in {"approved", "published"}:
                raise InvalidStateTransitionError("Publication requires the approved state.")

            if m.status == "published":
                return AgentVersion.from_stored(m)
            from database.repositories.bench_regression_repo import BenchRegressionRepository
            regression_repo = BenchRegressionRepository(session, self.db_manager.evidence_signer,
                self.permission_engine, self.approval_engine)
            baseline = regression_repo.current(context, m.blueprint_id)
            regression_repo.accept(context, passing_eval.id,
                expected_baseline_id=baseline.baseline_id if baseline else None,
                reason="Publication accepted through exact-payload Core human approval.", approval=approval)

            # 4. Transition to published
            published_model = agent_repo.update_version_status(
                context=context,
                version_id=version_id,
                target_status="published",
                published_by=context.actor.actor_id,
            )

            published_version = AgentVersion.from_stored(published_model)

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
                    "baseline_id": AgentRepository(session).get_blueprint(context, published_version.blueprint_id).bench_baseline_id,
                },
                session=session,
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
        self.permission_engine.enforce("agent:assign", context, context.organization_id, context.project_id)
        assignment_id = f"asgn_{uuid.uuid4().hex[:16]}"
        with self.db_manager.session(write=True) as session:
            repo = AgentRepository(session)
            version = repo.get_version(context, version_id, for_update=True)
            if version.status == "published":
                self.approval_engine.verify_approval(
                    context, "agent_version", version_id, version.payload_hash, session=session)
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
        self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
        with self.db_manager.session(write=True) as session:
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
