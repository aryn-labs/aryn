"""ARYN Core Run Coordinator.

The authoritative orchestrator for agent runs. Enforces permissions, budget checks,
audit trails, idempotency, persistent state machine, and lifecycle control around untrusted runtime adapters.
Frontend NEVER accesses Hermes directly; all requests flow through this coordinator.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rules 3, 4, 5, 8.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import importlib
import json
import uuid
from contextlib import nullcontext
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
from modules.core.workflows.ownership import ExecutionAuthority, ExecutionOwnershipError
from modules.core.errors import sanitize, public_error


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
        self._deadline_tasks = set()
        self.runtime_adapter = runtime_adapter
        self.db_manager = db_manager
        self.authority = ExecutionAuthority.for_engine(db_manager.engine) if db_manager else None
        self.permission_engine = permission_engine or getattr(db_manager, "permission_engine", None) or PermissionEngine(db_manager=db_manager)

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
        from packages.contracts.timestamps import utc_datetime
        return RunResult(
            run_id=row.id, status=RunStatus(row.status), output=sanitize(row.output or ""),
            usage=RunUsage(input_tokens=row.input_tokens, output_tokens=row.output_tokens, total_tokens=row.total_tokens,
                           availability=row.usage_availability, cost_usd=row.usage_cost_usd, cost_source=row.usage_cost_source),
            model=row.model, created_at=utc_datetime(row.created_at).timestamp(),
            completed_at=utc_datetime(row.completed_at).timestamp() if row.completed_at else None,
            error_message=row.error_message, error_code=row.error_code,
            requested_model=row.model, actual_model=row.actual_model,
            gateway=row.gateway, runtime_backend=row.runtime_backend, provider=row.actual_provider,
            assignment_id=row.assignment_id, agent_version_id=row.agent_version_id,
            agent_payload_hash=row.agent_payload_hash, assignment_transition_id=row.assignment_transition_id,
            execution_claim_verified=bool(row.execution_attestation),
            assignment_provenance_verified=bool(row.assignment_attestation),
            runtime_run_id=row.runtime_run_id, execution_provenance=json.loads(row.assignment_provenance_json) if row.assignment_provenance_json else None,
            effective_limits=json.loads(row.effective_limits_json), output_reference=f"core:run:{row.id}:output" if row.output is not None else None,
        )

    def _fence(self, row=None):
        if self.authority is None:
            raise ExecutionOwnershipError("Persistent execution authority is required.")
        self.authority.assert_valid()
        if row is not None and row.execution_owner_id != self.authority.owner_id:
            raise ExecutionOwnershipError("Stale run owner cannot mutate execution.")

    def _authorize_dispatch(self, run_id, context):
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            row = RunStateRepository(session).get_run(context, run_id)
            self._fence(row)
            self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id, session=session)
            if self._remaining(run_id, context) <= 0:
                raise TimeoutError("Core execution deadline exceeded.")
            if row.status not in {"started", "running"}:
                raise ExecutionOwnershipError("Claim is no longer eligible for dispatch.")

    async def _bounded(self, awaitable, seconds):
        task = asyncio.ensure_future(awaitable)
        try:
            done, _ = await asyncio.wait({task}, timeout=max(0, seconds))
            if not done:
                task.cancel()
                raise TimeoutError("Core execution deadline exceeded.")
            return task.result()
        finally:
            if not task.done():
                task.cancel()
                # A noncooperative runtime can still finish; it cannot write Core.
                task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)

    def _arm_deadline(self, run_id, context):
        async def watch():
            try:
                await asyncio.sleep(max(0, self._remaining(run_id, context)))
                self._fail_dispatch(run_id, context, TimeoutError())
            except (ExecutionOwnershipError, asyncio.CancelledError):
                return
            except Exception:
                import logging
                logging.getLogger("aryn.core.execution").error("core_deadline_persistence_unavailable run_id=%s", run_id)
        task = asyncio.create_task(watch())
        self._deadline_tasks.add(task)
        task.add_done_callback(self._deadline_tasks.discard)

    def _remaining(self, run_id, context):
        from database.repositories.run_state_repo import RunStateRepository
        from packages.contracts.timestamps import utc_datetime
        with self.db_manager.session() as session:
            row = RunStateRepository(session).get_run(context, run_id)
            self._fence(row)
            return (utc_datetime(row.deadline_at) - datetime.datetime.now(datetime.timezone.utc)).total_seconds()

    @staticmethod
    def request_fingerprint(request, context, mode):
        data = request.model_dump(mode="json", exclude={"idempotency_key"})
        data["metadata"].pop("idempotency_key", None)
        payload = {"request": data, "mode": mode, "actor_id": context.actor.actor_id,
                   "organization_id": context.organization_id, "project_id": context.project_id}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def _claim(self, request, context, mode, session=None, assignment_provenance=None):
        """Unique insert commits before runtime dispatch. Only its owner may execute."""
        self._fence()
        from database.repositories.exceptions import DuplicateEntityError
        from database.repositories.run_state_repo import RunStateRepository
        key = request.idempotency_key if request.idempotency_key is not None else request.metadata.get("idempotency_key")
        if key is not None and (not isinstance(key, str) or not key.strip() or len(key) > 255):
            raise IdempotencyConflictError("Idempotency key must be a nonempty bounded string.")
        fingerprint = self.request_fingerprint(request, context, mode)
        if not self.db_manager:
            raise RuntimeError("Persistent Core state is required for managed execution.")
        if key:
            with (nullcontext(session) if session is not None else self.db_manager.session()) as lookup:
                existing = RunStateRepository(lookup).get_run_by_idempotency_key(context, key)
                if existing:
                    if existing.request_hash != fingerprint:
                        raise IdempotencyConflictError("Idempotency conflict: key belongs to a different request or configuration.")
                    return False, self.stored_result(existing)
        spec = self.model_router.resolve_model(request.model)
        run_id = f"run_{uuid.uuid4().hex}"
        try:
            with (nullcontext(session) if session is not None else self.db_manager.session(write=True)) as active:
                self._fence()
                self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id, session=active)
                from database.repositories.budget_repo import BudgetRepository
                budgets = BudgetRepository(active).authority_budgets(context)
                total = min([self.budget_engine.default_rule.max_tokens_per_run, request.max_total_tokens or spec.context_window, spec.context_window, *[b.max_tokens_per_run for b in budgets]])
                if request.max_tokens > min(b.max_tokens_per_run for b in budgets):
                    raise BudgetExceededError("Requested output exceeds maximum allowed per run.")
                estimate = max(1, (len(request.prompt.encode()) + len((request.system_instructions or "").encode()) + 2) // 3)
                if request.max_tokens + estimate > min(b.max_tokens_per_run for b in budgets):
                    raise BudgetExceededError("Requested input/output exceeds maximum allowed per run.")
                if estimate >= total:
                    raise BudgetExceededError("Input admission estimate exceeds the effective token limit.")
                request.max_tokens = min(request.max_tokens, total - estimate)
                request.max_total_tokens = total
                request.max_input_tokens = min(request.max_input_tokens or total - 1, total - 1)
                if estimate > request.max_input_tokens:
                    raise BudgetExceededError("Input admission exceeds the effective input budget.")
                request.timeout_seconds = min(request.timeout_seconds, getattr(self.runtime_adapter, "timeout", request.timeout_seconds))
                cost_limit = min([request.max_cost_usd if request.max_cost_usd is not None else float("inf"), self.budget_engine.default_rule.max_cost_usd, *[b.max_cost_usd for b in budgets]])
                limits = {"max_total_tokens": total, "max_input_tokens": request.max_input_tokens,
                          "max_output_tokens": request.max_tokens, "timeout_seconds": request.timeout_seconds,
                          "input_estimate": estimate, "input_enforcement": "estimated_admission",
                          "total_enforcement": "measured_postflight", "output_enforcement": "provider_request_and_measured_postflight",
                          "max_turns": 1, "actor_id": context.actor.actor_id, "billing_category": "external_or_local",
                          "max_cost_usd": cost_limit, "cost_enforcement": "measured_if_supplied_external_cost_unavailable"}
                # Managed monetary dispatch requires an explicit price/ceiling contract;
                # external gateway/BYOK/local usage is never relabelled Managed AI.
                if spec.provider.value in {"gemini", "nous"}:
                    raise BudgetExceededError("Managed AI cost authority is unavailable for this route.")
                repo = RunStateRepository(active)
                run = repo.create_run(context, run_id, request.prompt, spec.model_id, spec.provider.value,
                                request.session_id, key, request_hash=fingerprint, execution_mode=mode)
                run._provenance_authorized = True
                run.execution_owner_id = self.authority.owner_id
                run.deadline_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=request.timeout_seconds)
                run.effective_limits_json = json.dumps(limits, sort_keys=True)
                BudgetRepository(active).reserve(context, run, total)
                if assignment_provenance:
                    run._provenance_authorized = True
                    provenance = {**assignment_provenance, "run_id": run_id, "request_hash": fingerprint,
                        "organization_id": context.organization_id, "project_id": context.project_id,
                        "requested_model": request.model}
                    run.assignment_id = provenance["assignment_id"]
                    run.agent_version_id = provenance["version_id"]
                    run.agent_payload_hash = provenance["payload_hash"]
                    run.assignment_transition_id = provenance["transition_id"]
                    run.assignment_provenance_json = json.dumps(provenance, sort_keys=True)
                    run.assignment_attestation = self.db_manager.evidence_signer.sign("assignment_run", provenance)
                    active.flush()
                from packages.contracts.timestamps import canonical_timestamp
                claim_evidence = {"run_id": run.id, "organization_id": run.organization_id, "project_id": run.project_id,
                    "request_hash": run.request_hash, "model": run.model, "provider": run.provider,
                    "owner_id": run.execution_owner_id, "mode": run.execution_mode,
                    "deadline_at": canonical_timestamp(run.deadline_at, stored=True),
                    "limits": limits, "assignment_attestation": run.assignment_attestation}
                run._provenance_authorized = True
                run.execution_claim_json = json.dumps(claim_evidence, sort_keys=True)
                run.execution_attestation = self.db_manager.evidence_signer.sign("execution_claim", claim_evidence)
                active.flush()
                repo.transition_status(context, run_id, "started")
                self.audit_logger.record("core.run.initiated" if mode == "direct" else "core.run.queued",
                                         context, run_id, AuditStatus.ALLOWED,
                                         {"model": spec.model_id, "provider": spec.provider.value, "prompt": request.prompt,
                                            **(assignment_provenance or {})}, session=active)
                captured = self.stored_result(run)
        except DuplicateEntityError:
            if session is not None:
                raise
            if not key:
                raise
            with self.db_manager.session() as session:
                existing = RunStateRepository(session).get_run_by_idempotency_key(context, key)
                if existing is None:
                    raise
                if existing.request_hash != fingerprint:
                    raise IdempotencyConflictError("Idempotency conflict: key belongs to a different request or configuration.") from None
                return False, self.stored_result(existing)
        return True, captured

    def _fail_dispatch(self, run_id, context, exc):
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            self._fence(row)
            if row.status in repo.TERMINAL_STATES:
                return
            error = public_error(exc, correlation_id=context.correlation_id, run_id=run_id)
            row.error_code = error["error_code"]
            target = "failed" if isinstance(exc, ModelIdentityError) else "outcome_unknown"
            repo.transition_status(context, run_id, target, error_message=error["message"])
            self.audit_logger.record("core.run." + target, context, run_id, AuditStatus.FAILED,
                                     {**error, "runtime_outcome": "identity_rejected" if target == "failed" else "unknown", "reservation_retained": True}, session=session)

    def _complete_dispatch(self, run_id, result, context):
        from database.repositories.budget_repo import BudgetRepository
        from database.repositories.run_state_repo import RunStateRepository
        from packages.contracts.timestamps import utc_datetime
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            self._fence(row)
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
            usage = result.usage
            measured = usage.availability == "measured"
            if measured and (min(usage.input_tokens, usage.output_tokens, usage.total_tokens) < 0
                    or usage.total_tokens != usage.input_tokens + usage.output_tokens):
                raise RuntimeError("Runtime usage is inconsistent.")
            limits = json.loads(row.effective_limits_json)
            breach = measured and (usage.total_tokens > limits["max_total_tokens"] or
                usage.input_tokens > limits["max_input_tokens"] or usage.output_tokens > limits["max_output_tokens"] or
                (usage.cost_usd is not None and usage.cost_source and usage.cost_usd > limits["max_cost_usd"]))
            expired = datetime.datetime.now(datetime.timezone.utc) >= utc_datetime(row.deadline_at)
            target = result.status.value
            if (target == "completed" and (not measured or (row.provider != "mock" and not result.actual_model))) or expired or target == "outcome_unknown":
                target = "outcome_unknown"
            elif breach:
                target = "failed"
            elif target not in {"completed", "cancelled", "failed"}:
                raise RuntimeError("Only a terminal runtime result can be settled.")
            row.runtime_run_id = result.run_id
            row.actual_model = result.actual_model or (result.model if row.provider == "mock" else None)
            row.gateway, row.runtime_backend, row.actual_provider = result.gateway, result.runtime_backend, result.provider
            row.error_code = "execution_limit_exceeded" if breach else "execution_evidence_unknown" if target == "outcome_unknown" else "runtime_failed" if target == "failed" else None
            # Settle even a confirmed partial failure, but never a missing usage estimate.
            BudgetRepository(session).settle(context, row, usage)
            session.flush()
            repo.transition_status(context, run_id, target, output=sanitize(result.output, credentials=getattr(self.db_manager, "protected_credentials", ())) if target == "completed" else None,
                usage=usage if measured else None,
                error_message="Execution evidence is incomplete or violates Core limits." if row.error_code else None)
            self.audit_logger.record("core.run." + target, context, run_id,
                AuditStatus.COMPLETED if target == "completed" else AuditStatus.CANCELLED if target == "cancelled" else AuditStatus.FAILED,
                {"requested_model": row.model, "actual_model": row.actual_model, "provider": row.actual_provider,
                 "usage_availability": row.usage_availability, "usage": usage.model_dump(), "error_code": row.error_code}, session=session)
            stored = self.stored_result(row)
            # Preserve operational Bench observations with the captured Core run ID.
            if result.execution_evidence is not None:
                stored.execution_evidence = sanitize({**result.execution_evidence, "run_id": run_id} if result.execution_evidence.get("run_id") == result.run_id else result.execution_evidence)
            return stored

    async def execute_managed_direct_turn(self, request: RunRequest, context: SecurityContext, *, _claimed=None, _allowed_tools=(), _execution_mode="direct") -> RunResult:
        request = request.model_copy(deep=True)
        try:
            self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        except PermissionDeniedError:
            self.audit_logger.record("core.run.denied", context, "run_request", AuditStatus.DENIED,
                                     {"error_code": "permission_denied", "prompt": request.prompt})
            raise
        try:
            owner, claimed = _claimed if _claimed is not None else self._claim(request, context, _execution_mode)
        except BudgetExceededError:
            self.audit_logger.record("core.run.budget_exceeded", context, "run_request", AuditStatus.DENIED,
                                     {"error_code": "budget_exceeded"})
            raise
        if not owner:
            if not claimed.execution_claim_verified:
                raise PermissionDeniedError("Historical execution claims are read-only and cannot authorize replay.")
            if claimed.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}:
                raise RunInProgressError(claimed.run_id, claimed.status.value)
            self.audit_logger.record("core.run.idempotent_cached", context, claimed.run_id,
                                     AuditStatus.COMPLETED if claimed.status == RunStatus.COMPLETED else AuditStatus.FAILED,
                                     {"status": claimed.status.value})
            return claimed
        try:
            caps = await self._bounded(self.runtime_adapter.capabilities(), self._remaining(claimed.run_id, context))
            if not caps.tools_confined or not set(caps.enabled_toolsets).issubset(_allowed_tools):
                raise PermissionDeniedError("Managed text execution requires all runtime toolsets disabled.")
            await self._bounded(self.runtime_adapter.require_model_available(request.model), self._remaining(claimed.run_id, context))
            self._authorize_dispatch(claimed.run_id, context)
            if hasattr(self.runtime_adapter, "execute_direct_turn"):
                result = await self._bounded(self.runtime_adapter.execute_direct_turn(request, context), self._remaining(claimed.run_id, context))
            else:
                runtime_id = await self._bounded(self.runtime_adapter.start_run(request, context), self._remaining(claimed.run_id, context))
                from database.repositories.run_state_repo import RunStateRepository
                with self.db_manager.session(write=True) as session:
                    row = RunStateRepository(session).get_run(context, claimed.run_id)
                    self._fence(row)
                    row.runtime_run_id = runtime_id
                    session.flush()
                while True:
                    result = await self._bounded(self.runtime_adapter.get_result(runtime_id, context), self._remaining(claimed.run_id, context))
                    if result.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}:
                        break
                    await self._bounded(asyncio.sleep(0.02), self._remaining(claimed.run_id, context))
            completed = self._complete_dispatch(claimed.run_id, result, context)
            self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
            return completed
        except BaseException as exc:
            exc.run_id = claimed.run_id
            self._fail_dispatch(claimed.run_id, context, exc)
            if isinstance(exc, ModelIdentityError) and "result" in locals():
                observation = result.model_copy(update={"run_id": claimed.run_id, "output": "", "raw_response": {}})
                if result.execution_evidence is not None:
                    observation.execution_evidence = sanitize({**result.execution_evidence, "run_id": claimed.run_id} if result.execution_evidence.get("run_id") == result.run_id else result.execution_evidence)
                exc.observed_result = observation
            raise

    async def execute_assigned_agent_turn(
        self,
        assignment_id: str,
        prompt: str,
        context: SecurityContext,
        idempotency_key: Optional[str] = None,
        *,
        expected_version_id: Optional[str] = None,
        claim_callback=None,
        workflow_reference: Optional[Dict[str, str]] = None,
    ) -> RunResult:
        """Executes a direct turn dispatched to an active AgentAssignment under Core governance."""
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        if not self.db_manager:
            raise RuntimeError("DatabaseManager is required for assigned agent execution.")

        from database.repositories.agent_repo import AgentRepository

        if idempotency_key:
            from database.repositories.run_state_repo import RunStateRepository
            with self.db_manager.session() as session:
                old = RunStateRepository(session).get_run_by_idempotency_key(context, idempotency_key)
                if old is not None:
                    if expected_version_id and old.agent_version_id != expected_version_id:
                        raise IdempotencyConflictError("Cached task differs from the pinned version.")
                    if old.prompt != prompt or old.assignment_id != assignment_id or json.loads(old.effective_limits_json).get("actor_id") != context.actor.actor_id:
                        raise IdempotencyConflictError("Key belongs to another input, actor or assignment.")
                    if not old.execution_attestation:
                        raise PermissionDeniedError("Historical execution claims cannot authorize replay.")
                    if old.status not in RunStateRepository.TERMINAL_STATES:
                        raise RunInProgressError(old.id, old.status)
                    return self.stored_result(old)
        from database.repositories.agent_activation_repo import AgentActivationRepository
        with self.db_manager.session(write=True) as session:
            repo = AgentRepository(session)
            activation = AgentActivationRepository(session, self.db_manager.evidence_signer, self.permission_engine)
            assignment = activation.lock_assignment(context, assignment_id)
            if expected_version_id and assignment.version_id != expected_version_id:
                raise PermissionDeniedError("Workflow assignment no longer matches the pinned version.")
            if assignment.status != "active":
                raise PermissionDeniedError("Agent assignment is not active.")
            version = repo.get_version(context, assignment.version_id)
            if version.blueprint_id != assignment.blueprint_id:
                raise PermissionDeniedError("Assignment blueprint differs from the version blueprint.")
            version = repo.get_version(context, assignment.version_id, for_update=True)
            if version.status != "published":
                raise RuntimeError("Assignment points to an unpublished version.")
            history = activation.history(context, assignment)
            reference = activation.known_good(context, version.id)
            if history and history[-1].publication_reference != reference:
                raise PermissionDeniedError("Activation evidence no longer matches publication authority.")
            if json.loads(version.tool_grants_json):
                raise PermissionDeniedError("Assigned text execution does not support tool grants.")
            provenance = {"assignment_id": assignment.id, "blueprint_id": assignment.blueprint_id,
                "version_id": version.id, "payload_hash": version.payload_hash,
                "transition_id": assignment.current_transition_id,
                "transition_hash": history[-1].attestation if history else None,
                "publication_id": reference["publication"]["publication_id"],
                "publication_hash": hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()}
            if workflow_reference is not None:
                provenance["workflow"] = dict(workflow_reference)
            from packages.contracts.agent import AgentVersion
            configuration = AgentVersion.from_stored(version)
            req = RunRequest(prompt=prompt, system_instructions=version.system_prompt, model=version.model,
                session_id=assignment_id, temperature=version.temperature, max_tokens=version.max_tokens,
                max_total_tokens=configuration.budget_policy.max_tokens_per_run, max_cost_usd=configuration.budget_policy.max_cost_usd,
                timeout_seconds=min(configuration.budget_policy.timeout_seconds, configuration.constraints.max_execution_time_seconds),
                idempotency_key=idempotency_key, metadata={**provenance,
                    "role_name": assignment.role_name, "division_id": assignment.division_id})
            claimed = self._claim(req, context, "direct", session=session, assignment_provenance=provenance)
            if claim_callback is not None:
                claim_callback(session, claimed[1])
        # The committed Core claim freezes version identity before dispatch. Rollback
        # affects only subsequent claims; no lock is held during runtime inference.
        return await self.execute_managed_direct_turn(req, context, _claimed=claimed)

    async def start_managed_run(self, request: RunRequest, context: SecurityContext) -> str:
        """Claim the Core ID before any asynchronous runtime start."""
        request = request.model_copy(deep=True)
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        owner, claimed = self._claim(request, context, "async")
        if not owner:
            if not claimed.execution_claim_verified:
                raise PermissionDeniedError("Historical execution claims cannot authorize replay.")
            return claimed.run_id
        try:
            caps = await self._bounded(self.runtime_adapter.capabilities(), self._remaining(claimed.run_id, context))
            if not caps.tools_confined or caps.enabled_toolsets:
                raise PermissionDeniedError("Managed asynchronous execution requires all runtime toolsets disabled.")
            await self._bounded(self.runtime_adapter.require_model_available(request.model), self._remaining(claimed.run_id, context))
            self._authorize_dispatch(claimed.run_id, context)
            runtime_id = await self._bounded(self.runtime_adapter.start_run(request, context), self._remaining(claimed.run_id, context))
            from database.repositories.run_state_repo import RunStateRepository
            with self.db_manager.session(write=True) as session:
                row = RunStateRepository(session).get_run(context, claimed.run_id)
                self._fence(row)
                row.runtime_run_id = runtime_id
                session.flush()
            self._arm_deadline(claimed.run_id, context)
            return claimed.run_id
        except BaseException as exc:
            exc.run_id = claimed.run_id
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
        if stored.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}:
            return stored
        if not runtime_id:
            return stored
        if self._remaining(run_id, context) <= 0:
            self._fail_dispatch(run_id, context, TimeoutError())
            return self._owned_run(run_id, context, "run:read")[0]
        try:
            result = await self._bounded(self.runtime_adapter.get_result(runtime_id, context), self._remaining(run_id, context))
        except BaseException as exc:
            self._fail_dispatch(run_id, context, exc)
            raise
        if result.run_id != runtime_id:
            raise RuntimeError("Runtime returned a mismatched run identifier.")
        if result.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}:
            completed = self._complete_dispatch(run_id, result, context)
            self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
            return completed
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            self._fence(row)
            if row.status not in repo.TERMINAL_STATES and result.status.value in repo.VALID_TRANSITIONS[row.status]:
                repo.transition_status(context, run_id, result.status.value)
            self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id, session=session)
            return self.stored_result(row)

    async def cancel_managed_run(self, run_id: str, context: SecurityContext) -> bool:
        """Return True only for cancellation proven by stored/runtime terminal state."""
        stored, runtime_id, mode = self._owned_run(run_id, context, "run:cancel")
        if stored.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}:
            return stored.status == RunStatus.CANCELLED
        if not runtime_id:
            self.audit_logger.record("core.run.cancellation.unavailable", context, run_id, AuditStatus.ATTEMPTED,
                                     {"reason": "No cancellable runtime run mapping", "cancellation_confirmed": False})
            return False
        self._fence()
        try:
            accepted = await self._bounded(self.runtime_adapter.cancel_run(runtime_id, context), self._remaining(run_id, context))
        except Exception as exc:
            self._fail_dispatch(run_id, context, exc)
            return False
        from database.repositories.run_state_repo import RunStateRepository
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            row = repo.get_run(context, run_id)
            self.permission_engine.enforce("run:cancel", context, context.organization_id, context.project_id, session=session)
            if row.status in repo.TERMINAL_STATES:
                return row.status == "cancelled"
            self._fence(row)
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
        trace = await self._bounded(self.runtime_adapter.get_trace(runtime_id, context), getattr(self.runtime_adapter, "timeout", 30))
        if trace.run_id != runtime_id:
            raise RuntimeError("Runtime returned a mismatched trace identifier.")
        self.permission_engine.enforce("run:trace", context, context.organization_id, context.project_id)
        credentials = getattr(self.db_manager, "protected_credentials", ())
        trace.events = sanitize(trace.events, credentials=credentials)
        trace.raw_trace = sanitize(trace.raw_trace, credentials=credentials)
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
        self._fence()
        recovered = []
        with self.db_manager.session(write=True) as session:
            repo = RunStateRepository(session)
            runs = repo.list_in_flight_runs(context.organization_id if context else None,
                                           context.project_id if context else None)
            for row in runs:
                if row.execution_owner_id == self.authority.owner_id:
                    continue
                ctx = context or SecurityContext(
                    organization_id=row.organization_id, project_id=row.project_id,
                    actor=Actor(actor_id="system_recovery", actor_type=ActorType.SYSTEM,
                                organization_id=row.organization_id, roles=[]),
                    correlation_id=f"recovery_{row.id}",
                )
                previous = row.status
                repo.transition_status(ctx, row.id, "outcome_unknown",
                                       error_message="Aborted due to system restart / crash recovery; runtime outcome unknown; cancellation not confirmed.")
                self.audit_logger.record("core.run.recovered", ctx, row.id, AuditStatus.FAILED,
                                         {"reason": "system_restart_recovery", "previous_status": previous,
                                          "runtime_outcome": "unknown", "cancellation_confirmed": False}, session=session)
                recovered.append({"run_id": row.id, "previous_status": previous, "status": "outcome_unknown",
                                  "runtime_outcome": "unknown", "cancellation_confirmed": False})
        return recovered
