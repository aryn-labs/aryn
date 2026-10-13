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
        from sqlalchemy.orm import object_session
        from database.schema import AuditEventModel
        from database.repositories.audit_repo import AuditRepository
        evidence = None
        session = object_session(row)
        if session is not None and row.execution_mode == "governed_agent" and row.status in {"completed", "failed"}:
            captured = session.query(AuditEventModel).filter_by(resource_id=row.id,
                organization_id=row.organization_id, project_id=row.project_id,
                event_type="core.run.evidence").all()
            if len(captured) > 1:
                raise PermissionDeniedError("Execution evidence identity is ambiguous.")
            if captured:
                if not AuditRepository(session).verify_authenticated_event(captured[0]):
                    raise PermissionDeniedError("Execution evidence is unverified.")
                receipt = json.loads(captured[0].redacted_payload_json)
                evidence = receipt["execution_evidence"]
                if evidence.get("run_id") != row.id:
                    raise PermissionDeniedError("Execution evidence scope differs.")
                if (receipt.get("status") != row.status or receipt.get("output_hash") !=
                        hashlib.sha256((row.output or "").encode()).hexdigest()):
                    raise PermissionDeniedError("Captured execution output or status differs.")
            elif row.execution_mode == "governed_agent" and row.status == "completed":
                raise PermissionDeniedError("Completed governed execution evidence is missing.")
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
            execution_evidence=evidence,
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
            if row.execution_mode == "agent_preview" and row.status == "started":
                RunStateRepository(session).transition_status(context, run_id, "running")
                self.audit_logger.record("factory.preview.dispatched", context, run_id,
                    AuditStatus.ALLOWED, {"requested_model": row.model}, session=session)

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
        # Preserve the existing fingerprint for historical text-only requests.
        if data.get("max_iterations") == 1 and data.get("max_tool_calls") == 0:
            data.pop("max_iterations", None)
            data.pop("max_tool_calls", None)
        data["metadata"].pop("idempotency_key", None)
        payload = {"request": data, "mode": mode, "actor_id": context.actor.actor_id,
                   "organization_id": context.organization_id, "project_id": context.project_id}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def _claim(self, request, context, mode, session=None, assignment_provenance=None, agent_configuration=None, allowed_tools=None):
        """Unique insert commits before runtime dispatch. Only its owner may execute."""
        self._fence()
        if agent_configuration is None and (request.max_iterations != 1 or request.max_tool_calls):
            raise PermissionDeniedError("Multi-step authority requires a captured agent version.")
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
                if agent_configuration is not None:
                    from packages.tool_adapters.fixture import NAME
                    from packages.contracts.bench import validate_output_contract
                    agent_configuration.verify_integrity(require_canonical=True)
                    validate_output_contract(agent_configuration.output_contract)
                    grants = set(agent_configuration.tool_grants)
                    if grants - {NAME} or not agent_configuration.tool_policy.deny_by_default:
                        raise PermissionDeniedError("Unregistered tools or non-denying policy.")
                    if allowed_tools is not None:
                        grants &= set(allowed_tools)
                    request.max_iterations = min(request.max_iterations,
                        agent_configuration.budget_policy.max_turns, self.budget_engine.default_rule.max_turns,
                        *[b.max_turns for b in budgets])
                    request.max_tool_calls = min(request.max_tool_calls, max(0, request.max_iterations - 1), 2)
                    limits.update({"max_turns": request.max_iterations, "max_tool_calls": request.max_tool_calls,
                        "tool_grants": sorted(grants), "agent_version_id": agent_configuration.id,
                        "agent_payload_hash": agent_configuration.payload_hash,
                        "output_contract": agent_configuration.output_contract.model_dump(mode="json"),
                        "max_output_tokens": min(total, request.max_tokens * request.max_iterations)})
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
            session.flush()
            target = "failed" if isinstance(exc, ModelIdentityError) else "outcome_unknown"
            repo.transition_status(context, run_id, target, error_message=error["message"])
            self.audit_logger.record("core.run." + target, context, run_id, AuditStatus.FAILED,
                                     {**error, "runtime_outcome": "identity_rejected" if target == "failed" else "unknown", "reservation_retained": True,
                                      **({"reported_model": sanitize(getattr(exc, "reported_model", None), credentials=getattr(self.db_manager, "protected_credentials", ())),
                                          "model_identity_stage": getattr(exc, "identity_stage", "core_settlement"),
                                          "gateway_response_fields": getattr(exc, "response_fields", [])} if isinstance(exc, ModelIdentityError) else {})}, session=session)

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
            invalid_output = None
            if result.status == RunStatus.COMPLETED and row.execution_mode != "bench" and limits.get("output_contract") is not None:
                from packages.contracts.bench import OutputContract, validate_output
                invalid_output, _ = validate_output(sanitize(result.output,
                    credentials=getattr(self.db_manager, "protected_credentials", ())), OutputContract.model_validate(limits["output_contract"]))
            breach = measured and (usage.total_tokens > limits["max_total_tokens"] or
                usage.input_tokens > limits["max_input_tokens"] or usage.output_tokens > limits["max_output_tokens"] or
                (usage.cost_usd is not None and usage.cost_source and usage.cost_usd > limits["max_cost_usd"]))
            expired = datetime.datetime.now(datetime.timezone.utc) >= utc_datetime(row.deadline_at)
            target = result.status.value
            if (target == "completed" and (not measured or (row.provider != "mock" and not result.actual_model))) or expired or target == "outcome_unknown":
                target = "outcome_unknown"
            elif breach:
                target = "failed"
            elif invalid_output:
                target = "failed"
            elif target not in {"completed", "cancelled", "failed"}:
                raise RuntimeError("Only a terminal runtime result can be settled.")
            row.runtime_run_id = result.run_id
            row.actual_model = result.actual_model or (result.model if row.provider == "mock" else None)
            row.gateway, row.runtime_backend, row.actual_provider = result.gateway, result.runtime_backend, result.provider
            row.error_code = "execution_limit_exceeded" if breach else "execution_evidence_unknown" if target == "outcome_unknown" else "runtime_failed" if target == "failed" else None
            if invalid_output and target == "failed":
                row.error_code = "invalid_output"
            elif target == "failed" and result.error_code in {"tool_permission_denied", "tool_input_invalid", "tool_failed", "execution_limit_exceeded"}:
                row.error_code = result.error_code
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
            if result.execution_evidence is not None and row.execution_mode == "governed_agent":
                # Only Core's in-process observations may enter the governed path.
                self.audit_logger.record("core.run.evidence", context, run_id, AuditStatus.COMPLETED,
                    {"execution_evidence": result.execution_evidence, "status": target,
                     "output_hash": hashlib.sha256((row.output or "").encode()).hexdigest()}, session=session)
            stored = self.stored_result(row)
            # Preserve operational Bench observations with the captured Core run ID.
            if result.execution_evidence is not None and row.execution_mode != "governed_agent":
                stored.execution_evidence = sanitize({**result.execution_evidence, "run_id": run_id} if result.execution_evidence.get("run_id") == result.run_id else result.execution_evidence)
            return stored

    async def verify_model(self, model, context, idempotency_key):
        """Explicit, metered text-only readiness check; no user prompt is dispatched here."""
        request = RunRequest(model=model, prompt="Reply with the word Ready.",
            system_instructions="Verify text generation only. Do not use tools.",
            max_tokens=128, timeout_seconds=60, temperature=0,
            idempotency_key=idempotency_key)
        return await self.execute_managed_direct_turn(request, context,
            _execution_mode="model_probe", _model_verification=True)

    async def execute_managed_direct_turn(self, request: RunRequest, context: SecurityContext, *, _claimed=None, _allowed_tools=(), _execution_mode="direct", _model_verification=False) -> RunResult:
        if _model_verification and (_execution_mode != "model_probe" or _allowed_tools or _claimed is not None
                or request.prompt != "Reply with the word Ready."
                or request.system_instructions != "Verify text generation only. Do not use tools."
                or request.max_tokens != 128 or request.timeout_seconds != 60
                or request.temperature != 0 or request.session_id or request.metadata):
            raise PermissionDeniedError("Only the fixed Core readiness probe may verify a model.")
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
            preflight = self.runtime_adapter.require_model_candidate if _model_verification else self.runtime_adapter.require_model_available
            await self._bounded(preflight(request.model), self._remaining(claimed.run_id, context))
            self._authorize_dispatch(claimed.run_id, context)
            if _model_verification:
                result = await self._bounded(self.runtime_adapter.execute_model_verification(request, context), self._remaining(claimed.run_id, context))
            elif hasattr(self.runtime_adapter, "execute_direct_turn"):
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
        automation_reference: Optional[Dict[str, str]] = None,
        max_total_tokens: Optional[int] = None,
        expected_transition_id: Optional[str] = None,
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
            if expected_transition_id is not None and assignment.current_transition_id != expected_transition_id:
                raise PermissionDeniedError("Scheduled assignment activation no longer matches the approved target.")
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
            provenance = {"assignment_id": assignment.id, "blueprint_id": assignment.blueprint_id,
                "version_id": version.id, "payload_hash": version.payload_hash,
                "transition_id": assignment.current_transition_id,
                "transition_hash": history[-1].attestation if history else None,
                "publication_id": reference["publication"]["publication_id"],
                "publication_hash": hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()}
            if workflow_reference is not None:
                provenance["workflow"] = dict(workflow_reference)
            if automation_reference is not None:
                provenance["automation"] = dict(automation_reference)
            from packages.contracts.agent import AgentVersion
            configuration = AgentVersion.from_stored(version)
            governed = bool(configuration.tool_grants)
            req = RunRequest(prompt=prompt, system_instructions=version.system_prompt, model=version.model,
                session_id=assignment_id, temperature=version.temperature, max_tokens=version.max_tokens,
                max_total_tokens=min(configuration.budget_policy.max_tokens_per_run, max_total_tokens) if max_total_tokens is not None else configuration.budget_policy.max_tokens_per_run, max_cost_usd=configuration.budget_policy.max_cost_usd,
                timeout_seconds=min(configuration.budget_policy.timeout_seconds, configuration.constraints.max_execution_time_seconds),
                idempotency_key=idempotency_key, metadata={**provenance,
                    "role_name": assignment.role_name, "division_id": assignment.division_id})
            if governed:
                req.max_iterations = min(configuration.budget_policy.max_turns, 3)
                req.max_tool_calls = min(req.max_iterations - 1, 2)
            claimed = self._claim(req, context, "governed_agent" if governed else "direct",
                session=session, assignment_provenance=provenance, agent_configuration=configuration)
            if claim_callback is not None:
                claim_callback(session, claimed[1])
        # The committed Core claim freezes version identity before dispatch. Rollback
        # affects only subsequent claims; no lock is held during runtime inference.
        if governed:
            return await self._execute_governed_turns(req, context, claimed)
        return await self.execute_managed_direct_turn(req, context, _claimed=claimed)

    async def execute_bench_agent_turn(self, request, context, version, allowed_tools):
        """Isolated evaluation authority for a persisted version, never a draft grant for user runs."""
        from database.repositories.agent_repo import AgentRepository
        with self.db_manager.session(write=True) as session:
            self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id, session=session)
            stored = AgentRepository(session).get_version(context, version.id, for_update=True)
            if stored.payload_hash != version.payload_hash or stored.status != "evaluating":
                raise PermissionDeniedError("Bench version authority differs.")
            if version.tool_grants:
                request.max_iterations = min(version.budget_policy.max_turns, 3)
                request.max_tool_calls = min(request.max_iterations - 1, 2)
            claimed = self._claim(request, context, "governed_agent" if version.tool_grants else "bench",
                session=session, agent_configuration=version, allowed_tools=allowed_tools)
        if version.tool_grants:
            return await self._execute_governed_turns(request, context, claimed)
        return await self.execute_managed_direct_turn(request, context, _claimed=claimed, _execution_mode="bench")

    def _tool_authority(self, run_id, context, iteration):
        from database.repositories.run_state_repo import RunStateRepository
        from database.repositories.agent_repo import AgentRepository
        from packages.contracts.agent import AgentVersion
        with self.db_manager.session(write=True) as session:
            row = RunStateRepository(session).get_run(context, run_id)
            self._fence(row)
            self.permission_engine.enforce("run:create", context, row.organization_id, row.project_id, session=session)
            limits = json.loads(row.effective_limits_json)
            from database.repositories.budget_repo import BudgetRepository
            current_budgets = BudgetRepository(session).authority_budgets(context)
            if (any(b.max_tokens_per_run < limits["max_total_tokens"] or b.max_turns < limits["max_turns"]
                    or b.max_cost_usd < limits["max_cost_usd"] for b in current_budgets)
                    or row.usage_settled or row.reserved_tokens != limits["max_total_tokens"]):
                raise PermissionDeniedError("Budget authority changed during execution.")
            version = AgentVersion.from_stored(AgentRepository(session).get_version(context, limits["agent_version_id"]))
            if (version.payload_hash != limits["agent_payload_hash"] or row.status not in {"started", "running"}
                    or self._remaining(run_id, context) <= 0 or iteration > limits["max_turns"]):
                raise PermissionDeniedError("Captured execution authority is stale.")
            if row.assignment_id:
                from database.repositories.agent_activation_repo import AgentActivationRepository
                active = AgentActivationRepository(session, self.db_manager.evidence_signer, self.permission_engine)
                assignment = active.lock_assignment(context, row.assignment_id)
                if assignment.status != "active" or version.status.value != "published":
                    raise PermissionDeniedError("Assignment authority revoked.")
                active.known_good(context, version.id)
            elif version.status.value != "evaluating":
                raise PermissionDeniedError("Bench authority revoked.")
            return limits

    async def _execute_governed_turns(self, request, context, claimed):
        from packages.contracts.runtime import ToolTurnRequest, ToolTurnResult, ToolExecutionContext
        from packages.tool_adapters import fixture
        import time
        owner, captured = claimed
        if not owner:
            if captured.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}:
                raise RunInProgressError(captured.run_id, captured.status.value)
            return captured
        run_id = captured.run_id
        usage = RunUsage(input_tokens=0, output_tokens=0, total_tokens=0)
        history, actions, seen_calls = [], [], set()
        tool_count = 0
        observed = None
        known_cost = True
        total_cost = 0.0
        try:
            caps = await self._bounded(self.runtime_adapter.capabilities(), self._remaining(run_id, context))
            if not caps.tools_confined or caps.enabled_toolsets or not caps.supports_governed_tool_turns:
                raise PermissionDeniedError("Runtime governed capability mismatch.")
            await self._bounded(self.runtime_adapter.require_model_available(request.model), self._remaining(run_id, context))
            model_caps = await self._bounded(self.runtime_adapter.model_capabilities(request.model), self._remaining(run_id, context))
            if model_caps.model != request.model or model_caps.tool_calling != "supported":
                raise PermissionDeniedError("Model tool-calling capability is unverified.")
            limits = self._tool_authority(run_id, context, 1)
            for iteration in range(1, limits["max_turns"] + 1):
                caps = await self._bounded(self.runtime_adapter.capabilities(), self._remaining(run_id, context))
                model_caps = await self._bounded(self.runtime_adapter.model_capabilities(request.model), self._remaining(run_id, context))
                if (not caps.tools_confined or caps.enabled_toolsets or not caps.supports_governed_tool_turns
                        or model_caps.model != request.model or model_caps.tool_calling != "supported"):
                    raise PermissionDeniedError("Continuation capability evidence is unavailable.")
                limits = self._tool_authority(run_id, context, iteration)
                prompt = request.prompt if not history else "Continue using the verified tool result."
                estimate = max(1, len(json.dumps([prompt, request.system_instructions, history,
                    [fixture.definition()] if limits["tool_grants"] else []]).encode()) // 3)
                remaining_output = min(request.max_tokens, limits["max_total_tokens"] - usage.total_tokens - estimate,
                    limits["max_output_tokens"] - usage.output_tokens)
                if remaining_output <= 0 or usage.input_tokens + estimate > limits["max_input_tokens"]:
                    if observed is None:
                        raise BudgetExceededError("Continuation exceeds admission budget.")
                    return self._complete_dispatch(run_id, observed.model_copy(update={"status": RunStatus.FAILED,
                        "usage": usage, "error_code": "execution_limit_exceeded", "execution_evidence": {
                            "run_id": run_id, "trace_complete": True, "actions": actions}}), context)
                step_request = request.model_copy(deep=True)
                step_request.prompt, step_request.session_id = prompt, None
                step_request.max_tokens = remaining_output
                step_request.timeout_seconds = self._remaining(run_id, context)
                step_request.metadata = {"initial_prompt": request.prompt}
                step_started = time.perf_counter()
                turn = await self._bounded(self.runtime_adapter.execute_tool_turn(ToolTurnRequest(
                    run_id=run_id, organization_id=context.organization_id, project_id=context.project_id,
                    iteration=iteration, request=step_request, history=history,
                    tool_names=limits["tool_grants"]), context), self._remaining(run_id, context))
                turn = ToolTurnResult.model_validate(turn.model_dump(mode="json"))
                observed = turn.result
                if turn.run_id != run_id or turn.iteration != iteration or observed.execution_evidence is not None:
                    raise PermissionDeniedError("Runtime step evidence differs from Core authority.")
                if (observed.model != request.model or observed.actual_model != request.model
                        or observed.requested_model != request.model or observed.gateway != "9Router"
                        or observed.runtime_backend != "Hermes"):
                    raise ModelIdentityError()
                measured = observed.usage
                if measured.availability != "measured" or measured.total_tokens != measured.input_tokens + measured.output_tokens:
                    raise RuntimeError("Step usage unavailable or inconsistent.")
                known_cost = known_cost and measured.cost_usd is not None and measured.cost_source is not None
                if measured.cost_usd is not None and measured.cost_source is not None:
                    total_cost += measured.cost_usd
                usage = RunUsage(input_tokens=usage.input_tokens + measured.input_tokens,
                    output_tokens=usage.output_tokens + measured.output_tokens, total_tokens=usage.total_tokens + measured.total_tokens,
                    cost_usd=total_cost if known_cost else None, cost_source="runtime_meter" if known_cost else None)
                from database.repositories.run_state_repo import RunStateRepository
                with self.db_manager.session(write=True) as session:
                    row = RunStateRepository(session).get_run(context, run_id)
                    self._fence(row)
                    self.audit_logger.record("core.run.iteration", context, run_id, AuditStatus.COMPLETED,
                        {"iteration": iteration, "runtime_run_id": observed.run_id, "requested_model": request.model,
                         "actual_model": observed.actual_model, "provider": observed.provider,
                         "reported_model": observed.reported_model, "usage": measured.model_dump(),
                         "duration_seconds": time.perf_counter() - step_started}, session=session)
                self._tool_authority(run_id, context, iteration)
                failure = None
                if (usage.total_tokens > limits["max_total_tokens"] or usage.input_tokens > limits["max_input_tokens"]
                        or usage.output_tokens > limits["max_output_tokens"] or measured.output_tokens > remaining_output
                        or total_cost > limits["max_cost_usd"]):
                    failure = "execution_limit_exceeded"
                elif not turn.tool_calls:
                    if observed.status != RunStatus.COMPLETED:
                        raise RuntimeError("Final turn is not completed.")
                else:
                    if observed.status != RunStatus.RUNNING:
                        raise RuntimeError("Tool proposal must remain pending.")
                    if not history:
                        history.append({"role": "user", "content": request.prompt})
                    history.append({"role": "assistant", "content": "", "tool_calls": [
                        {"id": call.call_id, "type": "function", "function": {"name": call.name,
                            "arguments": json.dumps(call.arguments)}} for call in turn.tool_calls]})
                    for call in turn.tool_calls:
                        limits = self._tool_authority(run_id, context, iteration)
                        tool_count += 1
                        code = "tool_permission_denied" if call.name != fixture.NAME or call.name not in limits["tool_grants"] else None
                        if call.call_id in seen_calls or tool_count > limits["max_tool_calls"] or iteration == limits["max_turns"]:
                            code = "execution_limit_exceeded"
                        self.audit_logger.record("core.tool.decision", context, run_id,
                            AuditStatus.DENIED if code else AuditStatus.ALLOWED,
                            {"tool_name": call.name, "capability": fixture.CAPABILITY if call.name == fixture.NAME else None,
                             "risk": fixture.RISK if call.name == fixture.NAME else None, "iteration": iteration,
                             "call_number": tool_count, "call_id": call.call_id, "error_code": code,
                             "input_hash": hashlib.sha256(json.dumps(call.arguments, sort_keys=True).encode()).hexdigest()})
                        if code:
                            failure = code
                            break
                        seen_calls.add(call.call_id)
                        started = time.perf_counter()
                        try:
                            verified_context = ToolExecutionContext(run_id=run_id, organization_id=context.organization_id,
                                project_id=context.project_id, deadline_at=time.time() + self._remaining(run_id, context),
                                call_number=tool_count)
                            data = fixture.execute(call.arguments, verified_context)
                            data = fixture.FixtureOutput.model_validate(data).model_dump()
                        except ValueError:
                            failure = "tool_input_invalid"
                            data = None
                        except LookupError:
                            failure = "tool_failed"
                            data = None
                        self._tool_authority(run_id, context, iteration)
                        # The result is created locally, schema validated, hashed and audited before continuation.
                        self.audit_logger.record("core.tool.result", context, run_id,
                            AuditStatus.FAILED if failure else AuditStatus.COMPLETED,
                            {"call_id": call.call_id, "tool_name": call.name, "error_code": failure,
                             "output_hash": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                             "duration_seconds": time.perf_counter() - started})
                        if failure:
                            break
                        actions.append({"action_id": call.call_id, "action": "fixture.read", "tool": fixture.NAME,
                            "capability": fixture.CAPABILITY})
                        history.append({"role": "tool", "name": call.name, "tool_call_id": call.call_id,
                            "content": json.dumps(data, sort_keys=True)})
                if failure or not turn.tool_calls:
                    final = observed.model_copy(update={"status": RunStatus.FAILED if failure else RunStatus.COMPLETED,
                        "usage": usage, "error_code": failure, "execution_evidence": {
                            "run_id": run_id, "trace_complete": True, "actions": actions,
                            "resources": {"iterations": iteration, "tool_call_attempts": tool_count}}})
                    completed = self._complete_dispatch(run_id, final, context)
                    self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
                    return completed
            raise RuntimeError("Iteration limit reached without final output.")
        except BaseException as exc:
            self._fail_dispatch(run_id, context, exc)
            exc.run_id = run_id
            raise

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
            if mode == "governed_agent":
                # A model thread may still be in flight. Fence future tool/turn
                # admission immediately without inventing provider cancellation.
                from database.repositories.run_state_repo import RunStateRepository
                with self.db_manager.session(write=True) as session:
                    repo = RunStateRepository(session)
                    row = repo.get_run(context, run_id)
                    self._fence(row)
                    self.permission_engine.enforce("run:cancel", context, context.organization_id, context.project_id, session=session)
                    if row.status not in repo.TERMINAL_STATES:
                        row.error_code = "execution_evidence_unknown"
                        repo.transition_status(context, run_id, "outcome_unknown",
                            error_message="Core stopped continuation; provider cancellation is unconfirmed.")
                        self.audit_logger.record("core.run.outcome_unknown", context, run_id, AuditStatus.ATTEMPTED,
                            {"reason": "governed_stop_requested", "cancellation_confirmed": False,
                             "reservation_retained": True}, session=session)
                return False
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
        if mode == "governed_agent" and stored.execution_evidence is not None:
            return RuntimeTrace(run_id=run_id, available=True, events=stored.execution_evidence["actions"],
                raw_trace={"complete": stored.execution_evidence["trace_complete"], "source": "signed_core_audit"})
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
