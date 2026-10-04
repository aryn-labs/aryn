"""ARYN Core Run Coordinator.

The authoritative orchestrator for agent runs. Enforces permissions, budget checks,
audit trails, idempotency, persistent state machine, and lifecycle control around untrusted runtime adapters.
Frontend NEVER accesses Hermes directly; all requests flow through this coordinator.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rules 3, 4, 5, 8.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from packages.contracts.core import Actor, ActorType, AuditStatus, SecurityContext
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeAdapter,
    RuntimeTrace,
)

if TYPE_CHECKING:
    from packages.model_adapters.router import ModelRouter

from modules.core.audit.logger import AuditLogger
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.usage.engine import BudgetEngine, BudgetExceededError


class RunCoordinator:
    """Core authority governing runtime execution and state transitions."""

    def __init__(
        self,
        runtime_adapter: RuntimeAdapter,
        permission_engine: Optional[PermissionEngine] = None,
        budget_engine: Optional[BudgetEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        model_router: Optional[Any] = None,
        db_manager: Optional[Any] = None,
    ) -> None:
        self.runtime_adapter = runtime_adapter
        self.db_manager = db_manager
        self.permission_engine = permission_engine or PermissionEngine(db_manager=db_manager)

        # If db_manager is passed, pass to audit and budget engines if not explicitly provided
        self.audit_logger = audit_logger or AuditLogger(db_manager=db_manager)
        self.budget_engine = budget_engine or BudgetEngine(db_manager=db_manager)

        if model_router is None:
            mr_cls = importlib.import_module("packages.model_adapters").ModelRouter
            self.model_router = mr_cls()
        else:
            self.model_router = model_router

    async def execute_managed_direct_turn(
        self,
        request: RunRequest,
        context: SecurityContext,
    ) -> RunResult:
        """Executes a direct turn under complete Core governance and state machine validation."""
        # 1. Authoritative Permissions Gate (Deterministic tenant, project, role, permission check)
        try:
            self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        except PermissionDeniedError as exc:
            self.audit_logger.record(
                event_type="core.run.denied",
                context=context,
                resource_id="run_request",
                status=AuditStatus.DENIED,
                payload={"reason": str(exc), "prompt": request.prompt},
            )
            raise

        # 2. Idempotency Check
        idempotency_key = request.idempotency_key or request.metadata.get("idempotency_key")
        if self.db_manager and idempotency_key:
            from database.repositories.run_state_repo import RunStateRepository
            with self.db_manager.session() as session:
                run_repo = RunStateRepository(session)
                existing = run_repo.get_run_by_idempotency_key(context, idempotency_key)
                if existing and existing.status == "completed":
                    self.audit_logger.record(
                        event_type="core.run.idempotent_cached",
                        context=context,
                        resource_id=existing.id,
                        status=AuditStatus.COMPLETED,
                        payload={"idempotency_key": idempotency_key},
                    )
                    return RunResult(
                        run_id=existing.id,
                        status=RunStatus.COMPLETED,
                        output=existing.output or "",
                        usage=RunUsage(
                            input_tokens=existing.input_tokens,
                            output_tokens=existing.output_tokens,
                            total_tokens=existing.total_tokens,
                        ),
                        model=existing.model,
                        created_at=existing.created_at.timestamp(),
                        completed_at=existing.completed_at.timestamp() if existing.completed_at else None,
                    )

        # 3. Model Routing & Policy Validation (ADR-005: No silent fallback)
        spec = self.model_router.resolve_model(request.model)

        # 4. Budget & Quota Preflight Check
        try:
            self.budget_engine.check_preflight(context)
        except BudgetExceededError as exc:
            self.audit_logger.record(
                event_type="core.run.budget_exceeded",
                context=context,
                resource_id="run_request",
                status=AuditStatus.DENIED,
                payload={"reason": str(exc)},
            )
            raise

        # 5. Persistent State - Initialize in 'queued' then 'started'
        run_id = f"run_{context.project_id}_{int(time.time() * 1000)}"
        if self.db_manager:
            from database.repositories.run_state_repo import RunStateRepository
            from database.repositories.exceptions import DuplicateEntityError
            from sqlalchemy.exc import IntegrityError
            try:
                with self.db_manager.session() as session:
                    run_repo = RunStateRepository(session)
                    run_repo.create_run(
                        context=context,
                        run_id=run_id,
                        prompt=request.prompt,
                        model=spec.model_id,
                        provider=spec.provider.value,
                        session_id=request.session_id,
                        idempotency_key=idempotency_key,
                    )
                    run_repo.transition_status(context, run_id, "started")
            except (IntegrityError, DuplicateEntityError):
                if idempotency_key:
                    with self.db_manager.session() as session:
                        run_repo = RunStateRepository(session)
                        existing = run_repo.get_run_by_idempotency_key(context, idempotency_key)
                        if existing and existing.status == "completed":
                            return RunResult(
                                run_id=existing.id,
                                status=RunStatus.COMPLETED,
                                output=existing.output or "",
                                usage=RunUsage(
                                    input_tokens=existing.input_tokens,
                                    output_tokens=existing.output_tokens,
                                    total_tokens=existing.total_tokens,
                                ),
                                model=existing.model,
                                created_at=existing.created_at.timestamp(),
                                completed_at=existing.completed_at.timestamp() if existing.completed_at else None,
                            )
                        elif existing:
                            run_id = existing.id
                else:
                    raise

        # 6. Pre-execution Audit
        self.audit_logger.record(
            event_type="core.run.initiated",
            context=context,
            resource_id=run_id,
            status=AuditStatus.ALLOWED,
            payload={
                "model": spec.model_id,
                "provider": spec.provider.value,
                "prompt": request.prompt,
            },
        )

        # 7. Dispatch to Runtime Adapter
        try:
            if hasattr(self.runtime_adapter, "execute_direct_turn"):
                result = await self.runtime_adapter.execute_direct_turn(request, context)
            else:
                adapter_run_id = await self.runtime_adapter.start_run(request, context)
                result = await self.runtime_adapter.get_result(adapter_run_id, context)

            if self.db_manager:
                result.run_id = run_id

            # 8. Post-execution Persistent State Transition to 'completed'
            if self.db_manager:
                from database.repositories.run_state_repo import RunStateRepository
                with self.db_manager.session() as session:
                    run_repo = RunStateRepository(session)
                    run_repo.transition_status(
                        context=context,
                        run_id=run_id,
                        target_status="completed",
                        output=result.output,
                        usage=result.usage,
                    )

            # 9. Budget Usage Recording
            self.budget_engine.record_usage(context, result.usage)

            # 10. Post-execution Audit
            self.audit_logger.record(
                event_type="core.run.completed",
                context=context,
                resource_id=result.run_id or run_id,
                status=AuditStatus.COMPLETED,
                payload={
                    "status": result.status.value,
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "total_tokens": result.usage.total_tokens,
                    "model": result.model,
                },
            )
            return result

        except Exception as exc:
            if self.db_manager:
                from database.repositories.run_state_repo import RunStateRepository
                try:
                    with self.db_manager.session() as session:
                        run_repo = RunStateRepository(session)
                        run_repo.transition_status(
                            context=context,
                            run_id=run_id,
                            target_status="failed",
                            error_message=str(exc),
                        )
                except Exception:
                    pass

            self.audit_logger.record(
                event_type="core.run.failed",
                context=context,
                resource_id=run_id,
                status=AuditStatus.FAILED,
                payload={"error": str(exc)},
            )
            raise

    async def execute_assigned_agent_turn(
        self,
        assignment_id: str,
        prompt: str,
        context: SecurityContext,
        idempotency_key: Optional[str] = None,
    ) -> RunResult:
        """Executes a direct turn dispatched to an active AgentAssignment under Core governance."""
        if not self.db_manager:
            raise RuntimeError("DatabaseManager is required for assigned agent execution.")

        from database.repositories.agent_repo import AgentRepository

        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            assignment = repo.get_assignment(context, assignment_id)
            version = repo.get_version(context, assignment.version_id)

            if version.status != "published":
                raise RuntimeError(
                    f"Agent assignment '{assignment_id}' points to unpublished version '{version.id}' (status: {version.status})."
                )

            system_prompt = version.system_prompt
            model = version.model
            blueprint_id = assignment.blueprint_id
            version_id = version.id
            role_name = assignment.role_name
            division_id = assignment.division_id

        req = RunRequest(
            prompt=prompt,
            system_instructions=system_prompt,
            model=model,
            idempotency_key=idempotency_key,
            metadata={
                "assignment_id": assignment_id,
                "blueprint_id": blueprint_id,
                "version_id": version_id,
                "role_name": role_name,
                "division_id": division_id,
            },
        )
        return await self.execute_managed_direct_turn(req, context)

    async def start_managed_run(
        self,
        request: RunRequest,
        context: SecurityContext,
    ) -> str:
        """Starts an async run through Core governance."""
        # 1. Authoritative Permissions Gate
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)

        # 2. Idempotency Check
        idempotency_key = request.idempotency_key or request.metadata.get("idempotency_key")
        if self.db_manager and idempotency_key:
            from database.repositories.run_state_repo import RunStateRepository
            with self.db_manager.session() as session:
                run_repo = RunStateRepository(session)
                existing = run_repo.get_run_by_idempotency_key(context, idempotency_key)
                if existing:
                    return existing.id

        # 3. Model Routing Policy Validation
        spec = self.model_router.resolve_model(request.model)

        # 4. Budget Check
        self.budget_engine.check_preflight(context)

        # 5. Dispatch to Runtime Adapter
        run_id = await self.runtime_adapter.start_run(request, context)

        # 6. Persistent State
        if self.db_manager:
            from database.repositories.run_state_repo import RunStateRepository
            with self.db_manager.session() as session:
                run_repo = RunStateRepository(session)
                run_repo.create_run(
                    context=context,
                    run_id=run_id,
                    prompt=request.prompt,
                    model=spec.model_id,
                    provider=spec.provider.value,
                    session_id=request.session_id,
                    idempotency_key=idempotency_key,
                )
                run_repo.transition_status(context, run_id, "started")

        # 7. Audit
        self.audit_logger.record(
            event_type="core.run.queued",
            context=context,
            resource_id=run_id,
            status=AuditStatus.ALLOWED,
            payload={"model": spec.model_id, "prompt": request.prompt},
        )

        return run_id

    async def get_managed_result(
        self,
        run_id: str,
        context: SecurityContext,
    ) -> RunResult:
        """Retrieves run results with permission checks and audit."""
        self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
        result = await self.runtime_adapter.get_result(run_id, context)

        if self.db_manager:
            from database.repositories.run_state_repo import RunStateRepository
            try:
                with self.db_manager.session() as session:
                    run_repo = RunStateRepository(session)
                    if result.status == RunStatus.COMPLETED:
                        run_repo.transition_status(
                            context=context,
                            run_id=run_id,
                            target_status="completed",
                            output=result.output,
                            usage=result.usage,
                        )
                    elif result.status == RunStatus.FAILED:
                        run_repo.transition_status(
                            context=context,
                            run_id=run_id,
                            target_status="failed",
                            error_message=result.error_message,
                        )
            except Exception:
                pass

        if result.status == RunStatus.COMPLETED:
            self.budget_engine.record_usage(context, result.usage)
            self.audit_logger.record(
                event_type="core.run.polled_completed",
                context=context,
                resource_id=run_id,
                status=AuditStatus.COMPLETED,
                payload={"tokens": result.usage.total_tokens},
            )
        return result

    async def cancel_managed_run(
        self,
        run_id: str,
        context: SecurityContext,
    ) -> bool:
        """Cancels a run with permission check and audit."""
        self.permission_engine.enforce("run:cancel", context, context.organization_id, context.project_id)
        cancelled = await self.runtime_adapter.cancel_run(run_id, context)

        if self.db_manager:
            from database.repositories.run_state_repo import RunStateRepository
            try:
                with self.db_manager.session() as session:
                    run_repo = RunStateRepository(session)
                    run_repo.transition_status(context=context, run_id=run_id, target_status="cancelled")
            except Exception:
                pass

        self.audit_logger.record(
            event_type="core.run.cancelled",
            context=context,
            resource_id=run_id,
            status=AuditStatus.CANCELLED,
            payload={"success": cancelled},
        )
        return cancelled

    async def get_managed_trace(
        self,
        run_id: str,
        context: SecurityContext,
    ) -> RuntimeTrace:
        """Retrieves execution trace with permission check."""
        self.permission_engine.enforce("run:trace", context, context.organization_id, context.project_id)
        trace = await self.runtime_adapter.get_trace(run_id, context)
        return trace

    def recover_in_flight_runs(self, context: Optional[SecurityContext] = None) -> List[Dict[str, Any]]:
        """Recovers runs left in non-terminal states after a system restart or crash.

        Transitions abandoned runs to 'failed' with descriptive cause and records audit events.
        """
        if not self.db_manager:
            return []

        recovered: List[Dict[str, Any]] = []
        from database.repositories.run_state_repo import RunStateRepository

        with self.db_manager.session() as session:
            repo = RunStateRepository(session)
            org_id = context.organization_id if context else None
            in_flight = repo.list_in_flight_runs(organization_id=org_id)

            for run in in_flight:
                ctx = context or SecurityContext(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    actor=Actor(
                        actor_id="system_recovery",
                        actor_type=ActorType.SYSTEM,
                        organization_id=run.organization_id,
                        roles=["admin"],
                    ),
                    correlation_id=f"recovery_{run.id}",
                )
                try:
                    prev_status = run.status
                    repo.transition_status(
                        ctx,
                        run.id,
                        target_status="failed",
                        error_message="Aborted due to system restart / crash recovery",
                    )
                    self.audit_logger.record(
                        event_type="core.run.recovered",
                        context=ctx,
                        resource_id=run.id,
                        status=AuditStatus.FAILED,
                        payload={"reason": "system_restart_recovery", "previous_status": prev_status},
                    )
                    recovered.append({"run_id": run.id, "previous_status": prev_status, "status": "failed"})
                except Exception as exc:
                    recovered.append({"run_id": run.id, "error": str(exc)})

        return recovered
