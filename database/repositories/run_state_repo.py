"""Repository for RunState with deterministic state transition validation and idempotency."""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import RunStateModel, utc_now
from packages.contracts.core import SecurityContext
from packages.contracts.runtime import RunStatus, RunUsage
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
        "queued": {"started", "cancelled", "failed"},
        "started": {"running", "completed", "cancelled", "failed"},
        "running": {"completed", "stopping", "cancelled", "failed"},
        "stopping": {"cancelled", "completed", "failed"},
        # Terminal states have NO outgoing transitions
        "completed": set(),
        "cancelled": set(),
        "failed": set(),
    }

    TERMINAL_STATES = frozenset({"completed", "cancelled", "failed"})

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
        run = self.session.query(RunStateModel).filter_by(id=run_id).first()
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
        return run

    def get_run_by_idempotency_key(self, context: SecurityContext, idempotency_key: str) -> Optional[RunStateModel]:
        """Finds existing run in the same project with given idempotency key."""
        return (
            self.session.query(RunStateModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
                idempotency_key=idempotency_key,
            )
            .first()
        )

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

        run.status = target
        run.updated_at = utc_now()

        if output is not None:
            run.output = output
        if error_message is not None:
            run.error_message = error_message
        if usage is not None:
            run.input_tokens = usage.input_tokens
            run.output_tokens = usage.output_tokens
            run.total_tokens = usage.total_tokens

        if target in self.TERMINAL_STATES:
            run.completed_at = utc_now()

        self.session.flush()
        return run

    def list_in_flight_runs(self, organization_id: Optional[str] = None) -> List[RunStateModel]:
        """Lists runs currently in non-terminal states (for restart recovery)."""
        query = self.session.query(RunStateModel).filter(
            RunStateModel.status.in_(["queued", "started", "running", "stopping"])
        )
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
        return query.all()
