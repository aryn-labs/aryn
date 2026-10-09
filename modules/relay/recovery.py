"""Trusted fixed database operation; no OS sandbox or host capability is claimed.

Only the supplied project-owned disposable demo fixture can change. The executor
and independent health verifier use separate transactions and observations.
"""

from database.schema import (
    DemoFixtureModel,
    RelayExecutionModel,
    RelayIncidentModel,
    RelayProposalModel,
)
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.workflows.ownership import ExecutionOwnershipError
from modules.core.records import now


class DisposableRecoveryExecutor:
    def __init__(self, records):
        self.records = records

    def apply(self, ctx, execution_id):
        records = self.records
        with records.db.session(write=True) as session:
            records.authorize(session, ctx, "run:create")
            _, execution = records.get(session, RelayExecutionModel, ctx, execution_id)
            records.core._fence()
            if (
                execution["owner_id"] != records.core.authority.owner_id
                or execution["status"] != "running"
            ):
                raise ExecutionOwnershipError(
                    "Recovery execution is no longer owned or dispatchable."
                )
            target, fixture = records.get(
                session, DemoFixtureModel, ctx, execution["target_id"], True
            )
            if (
                fixture["disposable"] is not True
                or fixture["revision"] != execution["before_revision"]
            ):
                raise InvalidStateTransitionError(
                    "Disposable target changed before the fixed action."
                )
            _, incident = records.get(
                session, RelayIncidentModel, ctx, execution["incident_id"], True
            )
            _, proposal = records.get(
                session, RelayProposalModel, ctx, execution["proposal_id"]
            )
            if (
                incident["status"] != "EXECUTING"
                or incident["proposal_id"] != proposal["id"]
                or proposal["action"] != "restart_demo"
            ):
                raise InvalidStateTransitionError(
                    "The exact allowlisted proposal is no longer current."
                )
            records.grounding(session, ctx, proposal["bundle_id"], fixture)
            approval = records.approvals.verify_approval(
                ctx,
                "relay_action",
                proposal["id"],
                execution["payload_hash"],
                session=session,
            )
            if approval.approval_id != execution["approval"]["approval_id"]:
                raise InvalidStateTransitionError(
                    "The original human receipt no longer authorizes this claim."
                )
            # This is the entire allowlisted effect: no action text is interpreted.
            fixture.update(
                running=True,
                revision=fixture["revision"] + 1,
                updated_at=now(),
                last_execution_id=execution_id,
            )
            records.put(session, ctx, target, fixture)
            row, execution = records.get(
                session, RelayExecutionModel, ctx, execution_id, True
            )
            execution.update(
                status="action_completed", after_revision=fixture["revision"]
            )
            records.put(session, ctx, row, execution)
            records.audit(
                session,
                ctx,
                "relay.demo.action_completed",
                execution_id,
                target_id=fixture["id"],
                target_revision=fixture["revision"],
            )
            records.approvals.verify_record(approval, session=session)
            records.authorize(session, ctx, "run:create")


class DemoHealthVerifier:
    @staticmethod
    def observe(fixture, execution, *, allow_unexecuted=False):
        if (
            allow_unexecuted
            and fixture["disposable"] is True
            and fixture["revision"] == execution["before_revision"]
            and fixture["last_execution_id"] is None
            and all(
                fixture[key] == execution["before_snapshot"][key]
                for key in ("running", "blocking_fault")
            )
            and not (fixture["running"] and not fixture["blocking_fault"])
        ):
            # Explicit reconciliation can establish an unchanged unhealthy
            # checkpoint. It cannot credit an unrelated action with recovery.
            return False
        if (
            fixture["disposable"] is not True
            or fixture["last_execution_id"] != execution["id"]
            or fixture["revision"] != execution["before_revision"] + 1
        ):
            raise InvalidStateTransitionError(
                "Health cannot verify an unrelated or superseded effect."
            )
        return fixture["running"] is True and fixture["blocking_fault"] is False
