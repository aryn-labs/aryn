"""Repository for RunState with deterministic state transition validation and idempotency."""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import RunStateModel, utc_now
from packages.contracts.core import SecurityContext
from packages.contracts.runtime import RunUsage
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    TenantIsolationError,
)


class RunStateRepository:
    """Enforces deterministic state machine and idempotency for agent runs."""

    # Deterministic State Machine Map
    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "queued": {"started", "cancelled", "failed", "outcome_unknown"},
        "started": {"running", "stopping", "completed", "cancelled", "failed", "outcome_unknown"},
        "running": {"completed", "stopping", "cancelled", "failed", "outcome_unknown"},
        "stopping": {"cancelled", "completed", "failed", "outcome_unknown"},
        # Terminal states have NO outgoing transitions
        "completed": set(),
        "cancelled": set(),
        "failed": set(),
        "outcome_unknown": set(),
    }

    TERMINAL_STATES = frozenset({"completed", "cancelled", "failed", "outcome_unknown"})

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self,
        context: SecurityContext,
        run_id: str,
        prompt: str,
        model: str,
        provider: str,
        session_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        request_hash: str = "",
        execution_mode: str = "legacy",
    ) -> RunStateModel:
        """Creates a new RunState in 'queued' status."""
        run = RunStateModel(
            id=run_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            session_id=session_id,
            status="queued",
            prompt=prompt,
            model=model,
            provider=provider,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            execution_mode=execution_mode,
        )
        self.session.add(run)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise DuplicateEntityError(
                f"Run with id '{run_id}' or idempotency key '{idempotency_key}' already exists in project '{context.project_id}'."
            ) from exc
        return run

    def get_run(self, context: SecurityContext, run_id: str) -> RunStateModel:
        query = self.session.query(RunStateModel).filter_by(id=run_id)
        if self.session.info.get("write"):
            # SQLite serializes writers with BEGIN IMMEDIATE. PostgreSQL must
            # refresh/lock the run before deciding terminal state or settlement;
            # locking only the budget leaves a stale usage_settled snapshot.
            query = query.with_for_update().populate_existing()
        run = query.first()
        if not run:
            raise EntityNotFoundError(f"Run '{run_id}' not found.")

        # Enforce tenant boundary
        if run.organization_id != context.organization_id:
            raise TenantIsolationError(
                f"Tenant boundary violation: Run '{run_id}' belongs to org '{run.organization_id}', "
                f"not context org '{context.organization_id}'."
            )
        # Enforce project boundary
        if run.project_id != context.project_id:
            raise TenantIsolationError(
                f"Project boundary violation: Run '{run_id}' belongs to project '{run.project_id}', "
                f"not context project '{context.project_id}'."
            )
        self.verify_assignment_provenance(run)
        self.verify_execution_claim(run)
        return run

    def verify_execution_claim(self, run):
        if not run.execution_claim_json:
            if run.execution_attestation or run.execution_owner_id:
                raise InvalidStateTransitionError("Execution claim is incomplete.")
            return False  # Historical read-only evidence, never new replay authority.
        from packages.contracts.timestamps import canonical_timestamp
        manager = self.session.info.get("db_manager")
        try:
            evidence = json.loads(run.execution_claim_json)
            bindings = {"run_id": run.id, "organization_id": run.organization_id, "project_id": run.project_id,
                "request_hash": run.request_hash, "model": run.model, "provider": run.provider,
                "owner_id": run.execution_owner_id, "mode": run.execution_mode,
                "deadline_at": canonical_timestamp(run.deadline_at, stored=True),
                "limits": json.loads(run.effective_limits_json), "assignment_attestation": run.assignment_attestation}
            if evidence != bindings or manager is None or not manager.evidence_signer.verify("execution_claim", evidence, run.execution_attestation):
                raise ValueError("Claim differs.")
            return True
        except (ValueError, TypeError):
            raise InvalidStateTransitionError("Captured Core execution claim is unverified.") from None

    def verify_assignment_provenance(self, run):
        if not run.assignment_provenance_json:
            if run.assignment_id or run.agent_version_id or run.agent_payload_hash or run.assignment_attestation:
                raise InvalidStateTransitionError("Run assignment provenance is incomplete.")
            return False
        manager = self.session.info.get("db_manager")
        try:
            evidence = json.loads(run.assignment_provenance_json)
            bindings = {"run_id": run.id, "organization_id": run.organization_id, "project_id": run.project_id,
                "assignment_id": run.assignment_id, "version_id": run.agent_version_id, "payload_hash": run.agent_payload_hash,
                "transition_id": run.assignment_transition_id, "request_hash": run.request_hash, "requested_model": run.model}
            if (not manager or any(evidence.get(k) != v for k, v in bindings.items())
                    or run.session_id != run.assignment_id or not manager.evidence_signer.verify(
                        "assignment_run", evidence, run.assignment_attestation)):
                raise ValueError("Run provenance mismatch.")
            return True
        except (ValueError, TypeError) as exc:
            raise InvalidStateTransitionError("Run assignment provenance is invalid.") from exc

    def get_run_by_idempotency_key(self, context: SecurityContext, idempotency_key: str) -> Optional[RunStateModel]:
        """Finds existing run in the same project with given idempotency key."""
        row = (
            self.session.query(RunStateModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
                idempotency_key=idempotency_key,
            )
            .first()
        )
        if row:
            self.verify_assignment_provenance(row)
            self.verify_execution_claim(row)
        return row

    def transition_status(
        self,
        context: SecurityContext,
        run_id: str,
        target_status: str,
        output: Optional[str] = None,
        usage: Optional[RunUsage] = None,
        error_message: Optional[str] = None,
    ) -> RunStateModel:
        """Transitions run status through validated state machine."""
        run = self.get_run(context, run_id)
        current_status = run.status.lower()
        target = target_status.lower()

        if target == current_status:
            return run  # No-op idempotent transition

        allowed_targets = self.VALID_TRANSITIONS.get(current_status, set())
        if target not in allowed_targets:
            raise InvalidStateTransitionError(
                f"Illegal state transition for run '{run_id}': cannot transition from '{current_status}' to '{target}'. "
                f"Allowed transitions from '{current_status}': {sorted(allowed_targets)}."
            )

        values = {"status": target, "updated_at": utc_now()}
        if output is not None:
            values["output"] = output
        if error_message is not None:
            values["error_message"] = error_message
        if usage is not None:
            values.update(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                          total_tokens=usage.total_tokens)

        if target in self.TERMINAL_STATES:
            values["completed_at"] = utc_now()
        updated = self.session.query(RunStateModel).filter_by(
            id=run_id, organization_id=context.organization_id,
            project_id=context.project_id, status=current_status,
        ).update(values, synchronize_session=False)
        if updated != 1:
            raise InvalidStateTransitionError("Run state changed concurrently; reload before retrying.")
        self.session.expire(run)
        self.session.refresh(run)
        return run

    def list_in_flight_runs(self, organization_id: Optional[str] = None, project_id: Optional[str] = None) -> List[RunStateModel]:
        """Lists runs currently in non-terminal states (for restart recovery)."""
        query = self.session.query(RunStateModel).filter(
            RunStateModel.status.in_(["queued", "started", "running", "stopping"])
        )
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
        if project_id:
            query = query.filter_by(project_id=project_id)
        return query.all()
