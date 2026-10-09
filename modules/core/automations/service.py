"""Durable Core schedules with exact approval and no retry after runtime admission.

One existing OS/advisory owner decides and dispatches. Neither timers nor the UI
provide authority. Transactions end before awaits; callbacks bind Core claims
atomically to occurrences before model dispatch. No native runtime jobs exist.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from database.schema import (
    AutomationDefinitionModel as DefinitionRow,
    AutomationOccurrenceModel as OccurrenceRow,
    AutomationEventModel as EventRow,
)
from database.repositories.exceptions import InvalidStateTransitionError
from database.repositories.agent_repo import AgentRepository
from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.run_state_repo import RunStateRepository
from modules.core.records import SignedRecords
from modules.core.workflows.executor import WorkflowExecutor, digest
from modules.core.workflows.ownership import ExecutionOwnershipError
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.history import HistoryUnverifiedError
from modules.core.automations.recurrence import (
    instant,
    next_instant,
    due_window,
    preview,
)
from packages.contracts.automation import (
    AutomationDefinition,
    AutomationOccurrence,
    AutomationEvent,
    AutomationInput,
)
from packages.contracts.workflow import StartWorkflow
from packages.contracts.core import ActorType

BUSY = {"dispatching", "waiting_review", "outcome_unknown"}
READY = {"queued", "retry_wait"}


def stamp(value):
    return instant(value).isoformat(timespec="microseconds")


class CoreAutomations(SignedRecords):
    def __init__(self, core, *, require_runtime=None, clock=None):
        super().__init__(core)
        self.workflows = WorkflowExecutor(core)
        self.require_runtime = require_runtime
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.tick_lock = asyncio.Lock()
        self.last_tick_at = None
        self.last_error = None

    def event(self, session, ctx, definition, name, occurrence=None, **details):
        self.add(
            session,
            ctx,
            EventRow,
            AutomationEvent,
            "automation_event",
            automation_id=definition["id"],
            occurrence_id=occurrence["id"] if occurrence else None,
            event=name,
            actor_id=ctx.actor.actor_id,
            details=self.clean(details),
        )
        self.audit(
            session,
            ctx,
            "core.automation." + name,
            definition["id"],
            occurrence_id=occurrence["id"] if occurrence else None,
            **self.clean(details),
        )

    def owner_context(self, definition, *, system=False):
        return self.permissions.identity_binder.create_trusted_context(
            "core_automation_recovery" if system else definition["owner_actor_id"],
            definition["organization_id"],
            definition["project_id"],
            actor_type=ActorType.SYSTEM if system else ActorType.USER,
        )

    def manage(self, session, ctx):
        self.core._fence()
        self.authorize(session, ctx, "version:approve")

    def target(self, session, ctx, target):
        # Follow the existing resource-before-membership lock order. Schedule
        # row locks never span this preflight; Core revalidates exact pins in
        # the eventual claim transaction, so a later activation change denies.
        self.permissions.enforce("run:create", ctx, ctx.organization_id, ctx.project_id)
        if target.kind == "agent":
            activation = AgentActivationRepository(
                session, self.db.evidence_signer, self.permissions
            )
            assignment = activation.lock_assignment(ctx, target.id)
            if (
                assignment.status != "active"
                or assignment.version_id != target.version_id
                or assignment.current_transition_id != target.activation_id
            ):
                raise InvalidStateTransitionError(
                    "Target assignment berbeda dari versi aktif yang dipin."
                )
            version = AgentRepository(session).get_version(
                ctx, target.version_id, for_update=True
            )
            if (
                version.status != "published"
                or version.payload_hash != target.payload_hash
            ):
                raise HistoryUnverifiedError("Target hash/publikasi tidak cocok.")
            activation.history(ctx, assignment)
            activation.known_good(ctx, version.id)
            from packages.contracts.agent import AgentVersion

            if AgentVersion.from_stored(version).tool_grants:
                raise PermissionDeniedError(
                    "Scheduled text target must have empty tool grants."
                )
        else:
            if target.activation_id is not None:
                raise InvalidStateTransitionError(
                    "Workflow targets use graph version pins, not assignment activation IDs."
                )
            version = self.workflows.version(session, ctx, target.version_id)
            if (
                version.workflow_id != target.id
                or version.digest != target.payload_hash
            ):
                raise HistoryUnverifiedError(
                    "Workflow/version/digest berbeda dari target yang dipin."
                )
            self.workflows.pinned(session, ctx, version.graph)
        self.authorize(session, ctx, "run:create")

    def preflight_target(self, ctx, target):
        with self.db.session(write=True) as session:
            self.core._fence()
            self.target(session, ctx, target)

    @staticmethod
    def configuration_hash(ctx, owner, body):
        return digest(
            {
                "organization_id": ctx.organization_id,
                "project_id": ctx.project_id,
                "owner_actor_id": owner,
                "configuration": body.model_dump(
                    mode="json", exclude={"expected_revision"}
                ),
            }
        )

    def save(self, ctx, body, identifier=None):
        clock = instant(self.clock())
        self.preflight_target(ctx, body.target)
        with self.db.session(write=True) as session:
            self.manage(session, ctx)
            body = body.model_copy(
                update={
                    "title": self.clean(body.title),
                    "input": self.clean(body.input),
                }
            )
            if identifier:
                row, definition = self.get(
                    session, DefinitionRow, ctx, identifier, True
                )
                if definition["owner_actor_id"] != ctx.actor.actor_id:
                    raise PermissionDeniedError(
                        "Only the owner can edit the approved schedule definition."
                    )
                if body.expected_revision != definition["revision"]:
                    raise InvalidStateTransitionError(
                        "Revision jadwal telah berubah. Muat ulang sebelum menyimpan."
                    )
                definition["revision"] += 1
                definition.update(
                    configuration=body.model_dump(mode="json"),
                    title=body.title,
                    payload_hash=self.configuration_hash(ctx, ctx.actor.actor_id, body),
                    status="paused",
                    next_run_at=stamp(next_instant(body.schedule, clock)),
                    updated_at=stamp(clock),
                )
                self.put(session, ctx, row, definition)
            else:
                if body.expected_revision is not None:
                    raise InvalidStateTransitionError(
                        "New schedules have no prior revision."
                    )
                _, definition = self.add(
                    session,
                    ctx,
                    DefinitionRow,
                    AutomationDefinition,
                    "automation",
                    title=body.title,
                    owner_actor_id=ctx.actor.actor_id,
                    revision=1,
                    configuration=body.model_dump(mode="json"),
                    payload_hash=self.configuration_hash(ctx, ctx.actor.actor_id, body),
                    next_run_at=stamp(next_instant(body.schedule, clock)),
                    updated_at=stamp(clock),
                )
            self.event(
                session,
                ctx,
                definition,
                "saved",
                revision=definition["revision"],
                payload_hash=definition["payload_hash"],
            )
            return definition

    def approval(self, session, ctx, definition):
        self.manage(session, ctx)
        if ctx.actor.actor_id != definition["owner_actor_id"]:
            raise PermissionDeniedError(
                "Schedule execution uses the current human owner's authority."
            )
        return self.db.approval_authority.verify_approval(
            ctx,
            "automation",
            definition["id"],
            definition["payload_hash"],
            session=session,
        )

    def approve(self, ctx, identifier, body):
        with self.db.session() as session:
            _, hint = self.get(session, DefinitionRow, ctx, identifier)
        self.preflight_target(
            ctx, AutomationInput.model_validate(hint["configuration"]).target
        )
        with self.db.session(write=True) as session:
            self.manage(session, ctx)
            _, definition = self.get(session, DefinitionRow, ctx, identifier, True)
            if (
                body.expected_revision != definition["revision"]
                or body.payload_hash != definition["payload_hash"]
            ):
                raise InvalidStateTransitionError(
                    "Persetujuan berbeda dari revision/hash jadwal."
                )
            if ctx.actor.actor_id != definition["owner_actor_id"]:
                raise PermissionDeniedError(
                    "Schedule owner must explicitly approve the exact configuration."
                )
            receipt = self.db.approval_authority.grant_approval(
                ctx,
                "automation",
                identifier,
                body.payload_hash,
                self.clean(body.reason),
                session=session,
            )
            self.event(
                session,
                ctx,
                definition,
                "approved",
                approval_id=receipt.approval_id,
                payload_hash=body.payload_hash,
            )
            return receipt.model_dump(mode="json")

    def state(self, ctx, identifier, body):
        if body.enabled:
            with self.db.session() as session:
                _, hint = self.get(session, DefinitionRow, ctx, identifier)
            self.preflight_target(
                ctx, AutomationInput.model_validate(hint["configuration"]).target
            )
        with self.db.session(write=True) as session:
            self.manage(session, ctx)
            row, definition = self.get(session, DefinitionRow, ctx, identifier, True)
            if body.expected_revision != definition["revision"]:
                raise InvalidStateTransitionError("Revision jadwal telah berubah.")
            if body.enabled:
                self.approval(session, ctx, definition)
            definition.update(
                status="enabled" if body.enabled else "paused",
                updated_at=stamp(self.clock()),
            )
            # Retain the durable cursor: resume applies the explicit missed policy.
            self.put(session, ctx, row, definition)
            self.event(session, ctx, definition, definition["status"])
            return definition

    def read(self, ctx, identifier):
        with self.db.session() as session:
            _, definition = self.get(session, DefinitionRow, ctx, identifier)
            body = AutomationInput.model_validate(definition["configuration"])
            approval_verified = False
            try:
                owner = self.owner_context(definition)
                self.approval(session, owner, definition)
                approval_verified = True
            except (PermissionDeniedError, RuntimeError, ValueError):
                pass
            except Exception as exc:
                from modules.core.approvals.engine import (
                    ApprovalRequiredError,
                    PayloadHashMismatchError,
                )

                if not isinstance(
                    exc, (ApprovalRequiredError, PayloadHashMismatchError)
                ):
                    raise
            return {
                **definition,
                "approval_verified": approval_verified,
                "preview": preview(
                    body.schedule,
                    max(
                        instant(self.clock()),
                        instant(definition["next_run_at"]) - timedelta(microseconds=1),
                    ),
                ),
                "scheduler": self.status(),
            }

    def status(self):
        self.core._fence()
        return {
            "authority": "core_single_owner",
            "last_tick_at": self.last_tick_at,
            "error_code": self.last_error,
            "local_device_off": "Tidak berjalan; missed policy diterapkan saat Core aktif kembali.",
            "availability_guarantee": False,
            "native_jobs": False,
        }

    def inventory(
        self,
        ctx,
        cls=DefinitionRow,
        *,
        identifier=None,
        after="",
        limit=25,
        q="",
        status="",
    ):
        with self.db.session() as session:
            filters = {}
            if identifier:
                self.get(session, DefinitionRow, ctx, identifier)
                filters["automation_id"] = identifier
            items, next_after = self.page(
                session, ctx, cls, after, limit, q, status, **filters
            )
            return {"items": items, "next": next_after}

    def targets(self, ctx, kind, after="", limit=25):
        from database.schema import AgentAssignmentModel, WorkflowVersionModel
        from packages.contracts.automation import AutomationTarget

        cls = AgentAssignmentModel if kind == "agent" else WorkflowVersionModel
        self.permissions.enforce(
            "version:approve", ctx, ctx.organization_id, ctx.project_id
        )
        with self.db.session() as session:
            query = session.query(cls).filter_by(
                organization_id=ctx.organization_id, project_id=ctx.project_id
            )
            if after:
                if query.filter(cls.id == after).first() is None:
                    raise PermissionDeniedError(
                        "Target pagination reference is outside this project."
                    )
                query = query.filter(cls.id > after)
            rows = query.order_by(cls.id).limit(limit + 1).all()
            items = []
            for row in rows[:limit]:
                try:
                    if kind == "agent":
                        version = AgentRepository(session).get_version(
                            ctx, row.version_id
                        )
                        target = AutomationTarget(
                            kind=kind,
                            id=row.id,
                            version_id=row.version_id,
                            payload_hash=version.payload_hash,
                            activation_id=row.current_transition_id,
                        )
                        label = row.role_name
                    else:
                        version = self.workflows.version(session, ctx, row.id)
                        target = AutomationTarget(
                            kind=kind,
                            id=version.workflow_id,
                            version_id=version.id,
                            payload_hash=version.digest,
                        )
                        label = version.workflow_id + " · " + str(version.revision)
                    self.preflight_target(ctx, target)
                    items.append(
                        {
                            "target": target.model_dump(mode="json"),
                            "label": label,
                            "available": True,
                            "reason": None,
                        }
                    )
                except (RuntimeError, ValueError, PermissionDeniedError):
                    items.append(
                        {
                            "target": None,
                            "label": row.id,
                            "available": False,
                            "reason": "Target unpublished/inactive or governed evidence unavailable.",
                        }
                    )
            return {
                "items": items,
                "next": rows[limit - 1].id if len(rows) > limit else None,
            }

    def occurrence(
        self, session, ctx, definition, key, scheduled_at, status="queued", error=None
    ):
        old = (
            session.query(OccurrenceRow)
            .filter_by(automation_id=definition["id"], occurrence_key=key)
            .first()
        )
        if old:
            return self.get(session, OccurrenceRow, ctx, old.id)[1], False
        _, occurrence = self.add(
            session,
            ctx,
            OccurrenceRow,
            AutomationOccurrence,
            "occurrence",
            automation_id=definition["id"],
            target_id=definition["configuration"]["target"]["id"],
            occurrence_key=key,
            scheduled_at=stamp(scheduled_at),
            definition_revision=definition["revision"],
            payload_hash=definition["payload_hash"],
            owner_id=self.core.authority.owner_id,
            status=status,
            run_kind=definition["configuration"]["target"]["kind"],
            error_code=error,
            created_at=stamp(self.clock()),
        )
        self.event(
            session,
            ctx,
            definition,
            "occurrence." + status,
            occurrence,
            scheduled_at=occurrence["scheduled_at"],
            error_code=error,
        )
        return occurrence, True

    def plan(self, identifier, org, project):
        # The signed definition supplies the owner. No browser/session impersonation.
        system = self.permissions.identity_binder.create_trusted_context(
            "core_automation_planner", org, project, actor_type=ActorType.SYSTEM
        )
        with self.db.session() as session:
            _, hint = self._verified(session, DefinitionRow, system, identifier)
        ctx = self.owner_context(hint)
        with self.db.session(write=True) as session:
            self.core._fence()
            # Match interactive changes and Core claim callbacks: membership
            # precedes schedule locks. Revoked owners still retain no effects.
            revoked = False
            try:
                self.manage(session, ctx)
            except PermissionDeniedError:
                revoked = True
            row, definition = self._verified(
                session, DefinitionRow, system, identifier, True
            )
            if definition["status"] != "enabled":
                return []
            try:
                if revoked:
                    raise PermissionDeniedError("Schedule owner authority revoked.")
                self.approval(session, ctx, definition)
            except Exception:
                definition.update(status="paused", updated_at=stamp(self.clock()))
                self.put(session, system, row, definition)
                self.event(session, system, definition, "authority_revoked")
                return []
            body = AutomationInput.model_validate(definition["configuration"])
            clock = instant(self.clock())
            due, following, omitted = due_window(
                body.schedule,
                definition["next_run_at"],
                clock,
                body.policy.catch_up_limit,
            )
            if omitted:
                self.event(
                    session,
                    ctx,
                    definition,
                    "missed.coalesced",
                    from_at=definition["next_run_at"],
                    through_at=stamp(omitted),
                    reason="bounded_latest_catchup; seven_day_window",
                )
            identifiers = []
            busy = (
                session.query(OccurrenceRow.id)
                .filter(
                    OccurrenceRow.automation_id == identifier,
                    OccurrenceRow.status.in_(BUSY),
                )
                .first()
            )
            queued = (
                session.query(func.count(OccurrenceRow.id))
                .filter(
                    OccurrenceRow.automation_id == identifier,
                    OccurrenceRow.status.in_(READY),
                )
                .scalar()
            )
            for at in due:
                missed = (clock - at).total_seconds() > 60
                status = (
                    "skipped" if missed and body.policy.missed == "skip" else "queued"
                )
                error = "missed" if status == "skipped" else None
                if status == "queued" and busy and body.policy.overlap == "skip":
                    status, error = "skipped", "overlap"
                if status == "queued" and queued >= 3:
                    status, error = "skipped", "overlap_queue_full"
                occurrence, fresh = self.occurrence(
                    session,
                    ctx,
                    definition,
                    "scheduled:" + stamp(at),
                    at,
                    status,
                    error,
                )
                if status == "queued":
                    queued += int(fresh)
                    identifiers.append(occurrence["id"])
            definition.update(next_run_at=stamp(following), updated_at=stamp(clock))
            self.put(session, ctx, row, definition)
            return identifiers

    async def manual(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            self.manage(session, ctx)
            _, definition = self.get(session, DefinitionRow, ctx, identifier, True)
            self.approval(session, ctx, definition)
            if (
                body.expected_revision != definition["revision"]
                or definition["status"] != "enabled"
            ):
                raise InvalidStateTransitionError(
                    "Jadwal belum enabled atau revision berubah."
                )
            occurrence, fresh = self.occurrence(
                session, ctx, definition, "manual:" + body.idempotency_key, self.clock()
            )
            if (
                not fresh
                and occurrence["definition_revision"] != definition["revision"]
            ):
                raise InvalidStateTransitionError(
                    "Manual key belongs to another revision."
                )
        if fresh:
            await self.dispatch(occurrence["id"], definition)
        with self.db.session() as session:
            return self.get(session, OccurrenceRow, ctx, occurrence["id"])[1]

    def update_occurrence(
        self, session, ctx, definition, row, occurrence, status, error=None
    ):
        occurrence.update(status=status, error_code=error)
        if status not in BUSY | READY:
            occurrence["completed_at"] = stamp(self.clock())
        self.put(session, ctx, row, occurrence)
        self.event(
            session,
            ctx,
            definition,
            "occurrence." + status,
            occurrence,
            run_id=occurrence["run_id"],
            error_code=error,
        )

    def daily_budget_exhausted(self, session, definition, identifier):
        day = instant(self.clock()).replace(hour=0, minute=0, second=0, microsecond=0)
        count = (
            session.query(func.count(OccurrenceRow.id))
            .filter(
                OccurrenceRow.automation_id == definition["id"],
                OccurrenceRow.admitted_at >= stamp(day),
                OccurrenceRow.id != identifier,
            )
            .scalar()
        )
        return count >= definition["configuration"]["policy"]["max_runs_per_day"]

    async def dispatch(self, identifier, hint):
        ctx = self.owner_context(hint)
        with self.db.session(write=True) as session:
            self.core._fence()
            _, definition = self.get(session, DefinitionRow, ctx, hint["id"], True)
            row, occurrence = self.get(session, OccurrenceRow, ctx, identifier, True)
            if (
                occurrence["status"] not in READY
                or occurrence["retry_at"]
                and instant(occurrence["retry_at"]) > instant(self.clock())
            ):
                return
            if definition["status"] != "enabled":
                return
            if (
                occurrence["payload_hash"] != definition["payload_hash"]
                or occurrence["definition_revision"] != definition["revision"]
            ):
                self.update_occurrence(
                    session,
                    ctx,
                    definition,
                    row,
                    occurrence,
                    "skipped",
                    "stale_definition",
                )
                return
            self.approval(session, ctx, definition)
            body = AutomationInput.model_validate(definition["configuration"])
            busy = (
                session.query(OccurrenceRow.id)
                .filter(
                    OccurrenceRow.automation_id == definition["id"],
                    OccurrenceRow.id != identifier,
                    OccurrenceRow.status.in_(BUSY),
                )
                .first()
            )
            if busy:
                if body.policy.overlap == "skip":
                    self.update_occurrence(
                        session, ctx, definition, row, occurrence, "skipped", "overlap"
                    )
                return
            if self.daily_budget_exhausted(session, definition, identifier):
                self.update_occurrence(
                    session,
                    ctx,
                    definition,
                    row,
                    occurrence,
                    "blocked",
                    "automation_daily_budget",
                )
                return
            occurrence.update(
                attempts=occurrence["attempts"] + 1,
                owner_id=self.core.authority.owner_id,
                retry_at=None,
            )
            self.update_occurrence(
                session, ctx, definition, row, occurrence, "dispatching"
            )
            parent, definition = self.get(
                session, DefinitionRow, ctx, definition["id"], True
            )
            definition.update(
                last_occurrence_id=identifier, updated_at=stamp(self.clock())
            )
            self.put(session, ctx, parent, definition)

        def capture(session, claimed):
            self.core._fence()
            _, active = self.get(session, DefinitionRow, ctx, definition["id"], True)
            self.approval(session, ctx, active)
            current, item = self.get(session, OccurrenceRow, ctx, identifier, True)
            if (
                active["status"] != "enabled"
                or active["payload_hash"] != occurrence["payload_hash"]
                or active["revision"] != occurrence["definition_revision"]
            ):
                raise PermissionDeniedError(
                    "Schedule was paused/edited before the Core claim committed."
                )
            if (
                item["owner_id"] != self.core.authority.owner_id
                or item["status"] != "dispatching"
                or item["run_id"]
            ):
                raise ExecutionOwnershipError(
                    "Occurrence claim is no longer dispatchable."
                )
            if self.daily_budget_exhausted(session, active, identifier):
                from modules.core.usage.engine import BudgetExceededError

                raise BudgetExceededError(
                    "Schedule daily admission budget exhausted at commit."
                )
            item["run_id"] = (
                claimed.run_id if body.target.kind == "agent" else claimed.id
            )
            item["admitted_at"] = stamp(self.clock())
            self.put(session, ctx, current, item)
            self.event(session, ctx, active, "claim.bound", item, run_id=item["run_id"])

        try:
            if self.require_runtime is not None:
                await self.require_runtime()
            with self.db.session(write=True) as session:
                self.target(session, ctx, body.target)
            reference = {
                "automation_id": definition["id"],
                "occurrence_id": identifier,
                "payload_hash": occurrence["payload_hash"],
            }
            if body.target.kind == "agent":
                await self.core.execute_assigned_agent_turn(
                    body.target.id,
                    body.input,
                    ctx,
                    "automation:" + identifier,
                    expected_version_id=body.target.version_id,
                    claim_callback=capture,
                    automation_reference=reference,
                    expected_transition_id=body.target.activation_id,
                    max_total_tokens=body.policy.max_tokens_per_task,
                )
            else:
                await self.workflows.start(
                    ctx,
                    body.target.id,
                    StartWorkflow(
                        version_id=body.target.version_id,
                        input=body.input,
                        idempotency_key="automation:" + identifier,
                        allow_remote_model=body.allow_remote_model,
                    ),
                    claim_callback=capture,
                    automation_reference=reference,
                    max_task_tokens=body.policy.max_tokens_per_task,
                )
        except Exception as exc:
            # Only explicit readiness failures *before any persisted Core claim*
            # can back off. Runtime/model admission failures never retry effects.
            from packages.contracts.runtime import (
                ModelUnavailableError,
                RuntimeGatewayError,
            )
            from fastapi import HTTPException
            from modules.core.usage.engine import BudgetExceededError

            system = self.owner_context(definition, system=True)
            with self.db.session(write=True) as session:
                self.core._fence()
                current, item = self._verified(
                    session, OccurrenceRow, system, identifier, True
                )
                if item["run_id"] is None:
                    retryable = (
                        isinstance(exc, (ModelUnavailableError, RuntimeGatewayError))
                        or isinstance(exc, HTTPException)
                        and exc.status_code == 503
                    )
                    if retryable and item["attempts"] < body.policy.max_attempts:
                        item["retry_at"] = stamp(
                            instant(self.clock())
                            + timedelta(
                                seconds=body.policy.backoff_seconds
                                * 2 ** (item["attempts"] - 1)
                            )
                        )
                        self.update_occurrence(
                            session,
                            system,
                            definition,
                            current,
                            item,
                            "retry_wait",
                            "runtime_unavailable",
                        )
                    else:
                        self.update_occurrence(
                            session,
                            system,
                            definition,
                            current,
                            item,
                            "blocked",
                            "core_budget_denied"
                            if isinstance(exc, BudgetExceededError)
                            else "dispatch_denied",
                        )
            self.refresh(identifier, definition)
            return
        self.refresh(identifier, definition)

    def refresh(self, identifier, definition, recovery=False):
        system = self.owner_context(definition, system=True)
        with self.db.session(write=True) as session:
            self.core._fence()
            row, occurrence = self._verified(
                session, OccurrenceRow, system, identifier, True
            )
            if occurrence["status"] not in BUSY:
                return
            status = None
            if occurrence["run_id"]:
                try:
                    if occurrence["run_kind"] == "agent":
                        run = RunStateRepository(session).get_run(
                            system, occurrence["run_id"]
                        )
                        if not run.execution_attestation:
                            raise HistoryUnverifiedError("Unverified occurrence run.")
                        status = run.status
                    else:
                        from database.schema import WorkflowRunModel

                        _, run = self.workflows.get(
                            session, WorkflowRunModel, system, occurrence["run_id"]
                        )
                        status = run["status"]
                except Exception:
                    status = "outcome_unknown"
                if status in {
                    "completed",
                    "failed",
                    "cancelled",
                    "rejected",
                    "outcome_unknown",
                    "waiting_review",
                }:
                    result = "failed" if status in {"cancelled", "rejected"} else status
                    if result != occurrence["status"]:
                        self.update_occurrence(
                            session,
                            system,
                            definition,
                            row,
                            occurrence,
                            result,
                            "core_" + status if result != "completed" else None,
                        )
                    return
            if recovery and occurrence["owner_id"] != self.core.authority.owner_id:
                self.update_occurrence(
                    session,
                    system,
                    definition,
                    row,
                    occurrence,
                    "outcome_unknown",
                    "interrupted_dispatch",
                )

    def recover(self):
        self.core._fence()
        with self.db.session() as session:
            active = (
                session.query(OccurrenceRow)
                .filter(OccurrenceRow.status.in_(BUSY))
                .order_by(OccurrenceRow.created_at)
                .limit(100)
                .all()
            )
            hints = []
            for occurrence in active:
                parent = session.get(DefinitionRow, occurrence.automation_id)
                system = self.permissions.identity_binder.create_trusted_context(
                    "core_automation_recovery",
                    parent.organization_id,
                    parent.project_id,
                    actor_type=ActorType.SYSTEM,
                )
                _, hint = self._verified(session, DefinitionRow, system, parent.id)
                hints.append((occurrence.id, hint))
        for identifier, hint in hints:
            self.refresh(identifier, hint, recovery=True)

    def reconcile(self, ctx, identifier, occurrence_id, body):
        with self.db.session(write=True) as session:
            self.manage(session, ctx)
            _, definition = self.get(session, DefinitionRow, ctx, identifier, True)
            row, occurrence = self.get(session, OccurrenceRow, ctx, occurrence_id, True)
            if (
                occurrence["automation_id"] != identifier
                or occurrence["status"] != "outcome_unknown"
            ):
                raise InvalidStateTransitionError(
                    "Only an unknown occurrence in this schedule can be reconciled."
                )
            # Explicit acknowledgement releases the schedule overlap hold, never
            # modifies a Core run/reservation or redispatches the unknown effect.
            self.update_occurrence(
                session,
                ctx,
                definition,
                row,
                occurrence,
                "reconciled",
                "operator_acknowledged_unknown",
            )
            self.event(
                session,
                ctx,
                definition,
                "reconciled.no_retry",
                occurrence,
                reason=self.clean(body.reason),
            )
            return occurrence

    async def tick(self):
        async with self.tick_lock:
            self.core._fence()
            self.last_tick_at, self.last_error = stamp(self.clock()), None
            self.recover()
            with self.db.session() as session:
                due = [
                    (row.id, row.organization_id, row.project_id)
                    for row in session.query(DefinitionRow)
                    .filter(
                        DefinitionRow.status == "enabled",
                        DefinitionRow.next_run_at <= stamp(self.clock()),
                    )
                    .order_by(DefinitionRow.next_run_at, DefinitionRow.id)
                    .limit(20)
                ]
            for identifier, org, project in due:
                self.plan(identifier, org, project)
            with self.db.session() as session:
                busy_definition = session.query(OccurrenceRow.automation_id).filter(
                    OccurrenceRow.status.in_(BUSY)
                )
                queued = (
                    session.query(OccurrenceRow)
                    .join(
                        DefinitionRow, OccurrenceRow.automation_id == DefinitionRow.id
                    )
                    .filter(
                        DefinitionRow.status == "enabled",
                        OccurrenceRow.status.in_(READY),
                        ~OccurrenceRow.automation_id.in_(busy_definition),
                    )
                    .order_by(OccurrenceRow.created_at, OccurrenceRow.id)
                    .limit(20)
                    .all()
                )
                hints = []
                for row in queued:
                    parent = session.get(DefinitionRow, row.automation_id)
                    system = self.permissions.identity_binder.create_trusted_context(
                        "core_automation_dispatch",
                        parent.organization_id,
                        parent.project_id,
                        actor_type=ActorType.SYSTEM,
                    )
                    _, hint = self._verified(session, DefinitionRow, system, parent.id)
                    hints.append((row.id, hint))
            for identifier, hint in hints:
                try:
                    await self.dispatch(identifier, hint)
                except PermissionDeniedError:
                    self.last_error = "authority_revoked"
            return self.status()
