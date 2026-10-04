"""ARYN Core Run Coordinator.

The authoritative orchestrator for agent runs. Enforces permissions, budget checks,
audit trails, idempotency, persistent state machine, and lifecycle control around untrusted runtime adapters.
Frontend NEVER accesses Hermes directly; all requests flow through this coordinator.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rules 3, 4, 5, 8.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import importlib
import time
import uuid
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


class IdempotencyConflictError(RuntimeError):
    pass


class RunInProgressError(RuntimeError):
    def __init__(self, run_id, status):
        self.run_id, self.status = run_id, status
        super().__init__(f"Run '{run_id}' is in progress ({status}); duplicate dispatch is forbidden.")


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

    @staticmethod
    def stored_result(row):
        return RunResult(
            run_id=row.id, status=RunStatus(row.status), output=row.output or "",
            usage=RunUsage(input_tokens=row.input_tokens, output_tokens=row.output_tokens, total_tokens=row.total_tokens),
            model=row.model, created_at=row.created_at.timestamp(),
            completed_at=row.completed_at.timestamp() if row.completed_at else None,
            error_message=row.error_message,
        )

    @staticmethod
    def request_fingerprint(request, context, mode):
        data = request.model_dump(mode="json", exclude={"idempotency_key"})
        data["metadata"].pop("idempotency_key", None)
        payload = {"request": data, "mode": mode, "actor_id": context.actor.actor_id,
                   "organization_id": context.organization_id, "project_id": context.project_id}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def _claim(self, request, context, mode):
        """Unique insert commits before runtime dispatch. Only its owner may execute."""
        from database.repositories.run_state_repo import RunStateRepository
        from database.repositories.exceptions import DuplicateEntityError
        key = request.idempotency_key or request.metadata.get("idempotency_key")
        fingerprint = self.request_fingerprint(request, context, mode)
        if not self.db_manager:
            raise RuntimeError("Persistent Core state is required for managed execution.")
        if key:
            with self.db_manager.session() as session:
                existing = RunStateRepository(session).get_run_by_idempotency_key(context, key)
                if existing:
                    if existing.request_hash != fingerprint:
                        raise IdempotencyConflictError("Idempotency conflict: key belongs to a different request or configuration.")
                    return False, self.stored_result(existing)
        spec = self.model_router.resolve_model(request.model)
        try:
            self.budget_engine.check_preflight(
                context, max(1000, request.max_tokens + (len(request.prompt) + len(request.system_instructions or "")) // 3))
        except BudgetExceededError as exc:
            self.audit_logger.record("core.run.budget_exceeded", context, "run_request", AuditStatus.DENIED, {"reason": str(exc)})
            raise
        run_id = f"run_{uuid.uuid4().hex}"
        try:
            with self.db_manager.session(write=True) as session:
                repo = RunStateRepository(session)
                repo.create_run(context, run_id, request.prompt, spec.model_id, spec.provider.value,
                                request.session_id, key, request_hash=fingerprint, execution_mode=mode)
                repo.transition_status(context, run_id, "started")
                self.audit_logger.record("core.run.initiated" if mode == "direct" else "core.run.queued",
                                         context, run_id, AuditStatus.ALLOWED,
                                         {"model": spec.model_id, "provider": spec.provider.value, "prompt": request.prompt}, session=session)
        except DuplicateEntityError:
            if not key:
                raise
            with self.db_manager.session() as session:
                existing = RunStateRepository(session).get_run_by_idempotency_key(context, key)
                if existing is None:
                    raise
                if existing.request_hash != fingerprint:
                    raise IdempotencyConflictError("Idempotency conflict: key belongs to a different request or configuration.")
                return False, self.stored_result(existing)
        return True, RunResult(run_id=run_id, status=RunStatus.STARTED, output="", model=spec.model_id, created_at=time.time())

    def _fail_dispatch(self, run_id, context, exc):
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            if row.status in repo.TERMINAL_STATES:
                return
            message = f"Execution interrupted ({type(exc).__name__}); runtime outcome may be unknown."
            repo.transition_status(context, run_id, "failed", error_message=message)
            self.audit_logger.record("core.run.failed", context, run_id, AuditStatus.FAILED,
                                     {"error_type": type(exc).__name__, "runtime_outcome": "unknown"}, session=session)

    def _complete_dispatch(self, run_id, result, context):
        from database.repositories.run_state_repo import RunStateRepository
        from database.repositories.budget_repo import BudgetRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            if row.status in repo.TERMINAL_STATES:
                return self.stored_result(row)
            if result.model != row.model:
                raise RuntimeError("Runtime reported a different model; silent fallback is forbidden.")
            if (min(result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) < 0
                    or result.usage.total_tokens != result.usage.input_tokens + result.usage.output_tokens):
                raise RuntimeError("Runtime usage is inconsistent.")
            row.runtime_run_id = result.run_id
            session.flush()
            repo.transition_status(context, run_id, "completed", output=result.output, usage=result.usage)
            BudgetRepository(session).record_usage(context, result.usage.total_tokens)
            self.audit_logger.record("core.run.completed", context, run_id, AuditStatus.COMPLETED,
                                     {"model": result.model, "input_tokens": result.usage.input_tokens,
                                      "output_tokens": result.usage.output_tokens, "total_tokens": result.usage.total_tokens}, session=session)
            result.run_id = run_id
            return result

    async def execute_managed_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        try:
            self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        except PermissionDeniedError as exc:
            self.audit_logger.record("core.run.denied", context, "run_request", AuditStatus.DENIED,
                                     {"reason": str(exc), "prompt": request.prompt})
            raise
        owner, claimed = self._claim(request, context, "direct")
        if not owner:
            if claimed.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                raise RunInProgressError(claimed.run_id, claimed.status.value)
            self.audit_logger.record("core.run.idempotent_cached", context, claimed.run_id,
                                     AuditStatus.COMPLETED if claimed.status == RunStatus.COMPLETED else AuditStatus.FAILED,
                                     {"status": claimed.status.value})
            return claimed
        try:
            if hasattr(self.runtime_adapter, "execute_direct_turn"):
                result = await self.runtime_adapter.execute_direct_turn(request, context)
            else:
                runtime_id = await self.runtime_adapter.start_run(request, context)
                result = await self.runtime_adapter.get_result(runtime_id, context)
            if result.status != RunStatus.COMPLETED:
                raise RuntimeError("Runtime did not complete the requested direct turn.")
            return self._complete_dispatch(claimed.run_id, result, context)
        except BaseException as exc:
            self._fail_dispatch(claimed.run_id, context, exc)
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
            if assignment.status != "active":
                raise PermissionDeniedError("Agent assignment is not active.")
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
            temperature = version.temperature
            max_tokens = version.max_tokens

        req = RunRequest(
            prompt=prompt,
            system_instructions=system_prompt,
            model=model,
            session_id=assignment_id,
            temperature=temperature,
            max_tokens=max_tokens,
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

    async def start_managed_run(self, request: RunRequest, context: SecurityContext) -> str:
        """Claim the Core ID before any asynchronous runtime start."""
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        owner, claimed = self._claim(request, context, "async")
        if not owner:
            return claimed.run_id
        try:
            runtime_id = await self.runtime_adapter.start_run(request, context)
            from database.repositories.run_state_repo import RunStateRepository
            with self.db_manager.session(write=True) as session:
                row = RunStateRepository(session).get_run(context, claimed.run_id)
                row.runtime_run_id = runtime_id
                session.flush()
            return claimed.run_id
        except BaseException as exc:
            self._fail_dispatch(claimed.run_id, context, exc)
            raise

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
                if self.permission_engine and getattr(self.permission_engine, "identity_binder", None):
                    self.permission_engine.identity_binder.bind_context(ctx)
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
