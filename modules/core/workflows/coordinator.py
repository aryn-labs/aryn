"""ARYN Core Run Coordinator.

The authoritative orchestrator for agent runs. Enforces permissions, budget checks,
audit trails, idempotency, persistent state machine, and lifecycle control around untrusted runtime adapters.
Frontend NEVER accesses Hermes directly; all requests flow through this coordinator.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rules 3, 4, 5, 8.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from packages.contracts.core import Actor, ActorType, AuditStatus, SecurityContext
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RuntimeAdapter,
    RuntimeTrace,
    RunUsage,
    ModelIdentityError,
)

if TYPE_CHECKING:
    pass

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
            requested_model=row.model, actual_model=row.actual_model,
            gateway=row.gateway, runtime_backend=row.runtime_backend, provider=row.actual_provider,
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
        from database.repositories.exceptions import DuplicateEntityError
        from database.repositories.run_state_repo import RunStateRepository
        key = request.idempotency_key if request.idempotency_key is not None else request.metadata.get("idempotency_key")
        if key is not None and (not isinstance(key, str) or not key.strip() or len(key) > 255):
            raise IdempotencyConflictError("Idempotency key must be a nonempty bounded string.")
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
        from database.repositories.budget_repo import BudgetRepository
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            if row.status in repo.TERMINAL_STATES:
                return self.stored_result(row)
            if result.model != row.model:
                raise ModelIdentityError()
            if row.provider == "9router" and (result.gateway != "9Router" or result.runtime_backend != "Hermes"
                    or result.requested_model != row.model or result.actual_model != row.model):
                raise ModelIdentityError()
            if result.gateway and (result.requested_model != row.model or result.actual_model != row.model):
                raise ModelIdentityError()
            if row.runtime_run_id and row.runtime_run_id != result.run_id:
                raise RuntimeError("Runtime returned a different run identifier.")
            if (min(result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) < 0
                    or result.usage.total_tokens != result.usage.input_tokens + result.usage.output_tokens):
                raise RuntimeError("Runtime usage is inconsistent.")
            row.runtime_run_id = result.run_id
            row.actual_model = result.model
            row.gateway, row.runtime_backend, row.actual_provider = result.gateway, result.runtime_backend, result.provider
            session.flush()
            repo.transition_status(context, run_id, "completed", output=result.output, usage=result.usage)
            BudgetRepository(session).record_usage(context, result.usage.total_tokens)
            self.audit_logger.record("core.run.completed", context, run_id, AuditStatus.COMPLETED,
                                     {"model": result.model, "requested_model": row.model, "actual_model": result.model,
                                      "gateway": result.gateway, "runtime_backend": result.runtime_backend, "provider": result.provider,
                                      "input_tokens": result.usage.input_tokens,
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
            caps = await self.runtime_adapter.capabilities()
            if not caps.tools_confined or caps.enabled_toolsets:
                raise PermissionDeniedError("Managed text execution requires all runtime toolsets disabled.")
            await self.runtime_adapter.require_model_available(request.model)
            if hasattr(self.runtime_adapter, "execute_direct_turn"):
                result = await self.runtime_adapter.execute_direct_turn(request, context)
            else:
                runtime_id = await self.runtime_adapter.start_run(request, context)
                from database.repositories.run_state_repo import RunStateRepository
                with self.db_manager.session(write=True) as session:
                    row = RunStateRepository(session).get_run(context, claimed.run_id)
                    row.runtime_run_id = runtime_id
                    row.execution_mode = "async"
                    session.flush()
                result = await self.runtime_adapter.get_result(runtime_id, context)
            if result.status != RunStatus.COMPLETED:
                raise RuntimeError("Runtime did not complete the requested direct turn.")
            completed = self._complete_dispatch(claimed.run_id, result, context)
            if completed.status != RunStatus.COMPLETED:
                raise RuntimeError("Core execution state was superseded; completion cannot be claimed.")
            return completed
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
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        if not self.db_manager:
            raise RuntimeError("DatabaseManager is required for assigned agent execution.")

        from database.repositories.agent_repo import AgentRepository

        with self.db_manager.session() as session:
            repo = AgentRepository(session)
            assignment = repo.get_assignment(context, assignment_id)
            if assignment.status != "active":
                raise PermissionDeniedError("Agent assignment is not active.")
            version = repo.get_version(context, assignment.version_id)
            if version.blueprint_id != assignment.blueprint_id:
                raise PermissionDeniedError("Assignment blueprint differs from the version blueprint.")

            if version.status != "published":
                raise RuntimeError(
                    f"Agent assignment '{assignment_id}' points to unpublished version '{version.id}' (status: {version.status})."
                )
            from modules.core.approvals.engine import ApprovalEngine
            ApprovalEngine(self.db_manager, permission_engine=self.permission_engine).verify_approval(
                context, "agent_version", version.id, version.payload_hash, session=session)
            import json
            if json.loads(version.tool_grants_json):
                raise PermissionDeniedError("Assigned text execution does not support tool grants.")

            system_prompt = version.system_prompt
            model = version.model
            blueprint_id = assignment.blueprint_id
            version_id = version.id
            payload_hash = version.payload_hash
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
                "payload_hash": payload_hash,
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
            caps = await self.runtime_adapter.capabilities()
            if not caps.tools_confined or caps.enabled_toolsets:
                raise PermissionDeniedError("Managed asynchronous execution requires all runtime toolsets disabled.")
            await self.runtime_adapter.require_model_available(request.model)
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

    def _owned_run(self, run_id, context, action):
        self.permission_engine.enforce(action, context, context.organization_id, context.project_id)
        if not self.db_manager:
            raise RuntimeError("Persistent run ownership is required.")
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session() as session:
            row = RunStateRepository(session).get_run(context, run_id)
            return self.stored_result(row), row.runtime_run_id, row.execution_mode

    async def get_managed_result(self, run_id: str, context: SecurityContext) -> RunResult:
        """Authorize the stored Core run before translating its ID to a runtime ID."""
        stored, runtime_id, mode = self._owned_run(run_id, context, "run:read")
        if stored.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return stored
        if mode != "async" or not runtime_id:
            return stored
        result = await self.runtime_adapter.get_result(runtime_id, context)
        if result.run_id != runtime_id:
            raise RuntimeError("Runtime returned a mismatched run identifier.")
        if result.status == RunStatus.COMPLETED:
            return self._complete_dispatch(run_id, result, context)
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            if row.status in repo.TERMINAL_STATES:
                return self.stored_result(row)
            if result.model and result.model != row.model:
                raise RuntimeError("Runtime reported a different model.")
            target = result.status.value
            if target in {"cancelled", "failed"}:
                if (min(result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) < 0
                        or result.usage.total_tokens != result.usage.input_tokens + result.usage.output_tokens):
                    raise RuntimeError("Runtime usage is inconsistent.")
                repo.transition_status(context, run_id, target, usage=result.usage,
                                       error_message="Runtime melaporkan kegagalan eksekusi." if target == "failed" else None)
                from database.repositories.budget_repo import BudgetRepository
                BudgetRepository(session).record_usage(context, result.usage.total_tokens)
                self.audit_logger.record("core.run.cancelled" if target == "cancelled" else "core.run.failed",
                                         context, run_id, AuditStatus.CANCELLED if target == "cancelled" else AuditStatus.FAILED,
                                         {"runtime_confirmed": True, "runtime_run_id": runtime_id}, session=session)
            elif target in repo.VALID_TRANSITIONS.get(row.status, set()):
                repo.transition_status(context, run_id, target)
            return self.stored_result(row)

    async def cancel_managed_run(self, run_id: str, context: SecurityContext) -> bool:
        """Return True only for cancellation proven by stored/runtime terminal state."""
        stored, runtime_id, mode = self._owned_run(run_id, context, "run:cancel")
        if stored.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return stored.status == RunStatus.CANCELLED
        if mode != "async" or not runtime_id:
            self.audit_logger.record("core.run.cancellation.unavailable", context, run_id, AuditStatus.ATTEMPTED,
                                     {"reason": "No cancellable runtime run mapping", "cancellation_confirmed": False})
            return False
        accepted = await self.runtime_adapter.cancel_run(runtime_id, context)
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            if row.status in repo.TERMINAL_STATES:
                return row.status == "cancelled"
            if accepted and row.status != "stopping":
                repo.transition_status(context, run_id, "stopping")
            self.audit_logger.record("core.run.cancellation.requested", context, run_id,
                                     AuditStatus.ATTEMPTED if accepted else AuditStatus.FAILED,
                                     {"accepted": accepted, "cancellation_confirmed": False}, session=session)
        if not accepted:
            return False
        try:
            confirmed = await self.get_managed_result(run_id, context)
        except Exception:
            # The stop acknowledgment is not proof; leave stopping for later polling/recovery.
            return False
        return confirmed.status == RunStatus.CANCELLED

    async def get_managed_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        stored, runtime_id, mode = self._owned_run(run_id, context, "run:trace")
        if mode != "async" or not runtime_id:
            return RuntimeTrace(run_id=run_id, available=False,
                                unavailability_reason="Trace runtime untuk eksekusi langsung belum tersedia. Audit Core tetap tersedia.")
        trace = await self.runtime_adapter.get_trace(runtime_id, context)
        if trace.run_id != runtime_id:
            raise RuntimeError("Runtime returned a mismatched trace identifier.")
        trace.run_id = run_id
        if not trace.available:
            trace.events = []
            trace.raw_trace = None
        return trace

    def recover_in_flight_runs(self, context: Optional[SecurityContext] = None) -> List[Dict[str, Any]]:
        """Startup reconciliation marks local outcome unknown, never cancellation success.

        The unscoped form is an internal startup operation; it is not exposed by the API.
        A caller supplying a context is authorized and restricted to that exact project.
        """
        if not self.db_manager:
            return []
        if context is not None:
            self.permission_engine.enforce("run:cancel", context, context.organization_id, context.project_id)
        from database.repositories.run_state_repo import RunStateRepository
        recovered = []
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            runs = repo.list_in_flight_runs(context.organization_id if context else None,
                                           context.project_id if context else None)
            for row in runs:
                ctx = context or SecurityContext(
                    organization_id=row.organization_id, project_id=row.project_id,
                    actor=Actor(actor_id="system_recovery", actor_type=ActorType.SYSTEM,
                                organization_id=row.organization_id, roles=[]),
                    correlation_id=f"recovery_{row.id}",
                )
                previous = row.status
                repo.transition_status(ctx, row.id, "failed",
                                       error_message="Aborted due to system restart / crash recovery; runtime outcome unknown; cancellation not confirmed.")
                self.audit_logger.record("core.run.recovered", ctx, row.id, AuditStatus.FAILED,
                                         {"reason": "system_restart_recovery", "previous_status": previous,
                                          "runtime_outcome": "unknown", "cancellation_confirmed": False}, session=session)
                recovered.append({"run_id": row.id, "previous_status": previous, "status": "failed",
                                  "runtime_outcome": "unknown", "cancellation_confirmed": False})
        return recovered
