"""Server-owned incident state, Core approvals and verified disposable recovery."""

from database.schema import (
    DemoFixtureModel as FixtureRow,
    DemoObservationModel as ObservationRow,
    RelaySignalModel as SignalRow,
    RelayIncidentModel as IncidentRow,
    RelayEventModel as EventRow,
    RelayInvestigationModel as InvestigationRow,
    RelayProposalModel as ProposalRow,
    RelayExecutionModel as ExecutionRow,
    RelayVerificationModel as VerificationRow,
    RelayCapsuleModel as CapsuleRow,
)
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.records import SignedRecords, digest, now
from modules.core.approvals.engine import (
    PayloadHashMismatchError,
    ApprovalRequiredError,
)
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.workflows.coordinator import IdempotencyConflictError
from modules.core.workflows.ownership import ExecutionOwnershipError
from packages.contracts.intelligence import (
    DemoFixture,
    DemoObservation,
    Signal,
    Incident,
    IncidentTimeline,
    Investigation,
    ActionProposal,
    RecoveryExecution,
    RecoveryVerification,
    IncidentCapsule,
    CreateBundle,
    Hypothesis,
)
from modules.relay.recovery import DisposableRecoveryExecutor, DemoHealthVerifier


TRANSITIONS = {
    "OPEN": {"INVESTIGATING"},
    "INVESTIGATING": {"INVESTIGATING", "PROPOSED"},
    "PROPOSED": {"INVESTIGATING", "PROPOSED", "EXECUTING"},
    "EXECUTING": {"RECOVERED", "DEGRADED", "OUTCOME_UNKNOWN"},
    "DEGRADED": {"INVESTIGATING"},
    "RECOVERED": {"CLOSED"},
    "OUTCOME_UNKNOWN": {"RECOVERED", "DEGRADED"},
    "CLOSED": set(),
}


class RelayService(SignedRecords):
    def __init__(self, core, brief):
        super().__init__(core)
        self.brief = brief
        self.approvals = self.db.approval_authority
        self.executor = DisposableRecoveryExecutor(self)

    def event(self, session, ctx, incident, event, old=None, reference_id=None):
        self.add(
            session,
            ctx,
            EventRow,
            IncidentTimeline,
            "incident_event",
            incident_id=incident["id"],
            sequence=incident["revision"],
            event=event,
            from_status=old,
            to_status=incident["status"],
            actor_id=ctx.actor.actor_id,
            reference_id=reference_id,
        )
        self.audit(
            session,
            ctx,
            "relay." + event,
            incident["id"],
            status=incident["status"],
            reference_id=reference_id,
        )

    def transition(self, session, ctx, row, incident, target, event, reference_id=None):
        self.core._fence()
        old = incident["status"]
        if target not in TRANSITIONS[old]:
            raise InvalidStateTransitionError(
                "Incident state cannot make that transition."
            )
        incident.update(
            status=target, revision=incident["revision"] + 1, updated_at=now()
        )
        self.put(session, ctx, row, incident)
        self.event(session, ctx, incident, event, old, reference_id)

    def observation(self, session, ctx, fixture, reason):
        _, observed = self.add(
            session,
            ctx,
            ObservationRow,
            DemoObservation,
            "observation",
            target_id=fixture["id"],
            target_revision=fixture["revision"],
            running=fixture["running"],
            blocking_fault=fixture["blocking_fault"],
            healthy=fixture["running"] and not fixture["blocking_fault"],
            reason=reason,
        )
        source = self.brief.ingest_in_session(
            session,
            ctx,
            {"kind": "demo_observation", "id": observed["id"]},
            "Disposable demo health observation",
        )
        return observed, source

    def create_fixture(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:create")
            _, fixture = self.add(
                session,
                ctx,
                FixtureRow,
                DemoFixture,
                "demo",
                name=self.clean(body.name),
                revision=1,
                running=True,
                blocking_fault=False,
                updated_at=now(),
            )
            observed, source = self.observation(session, ctx, fixture, "created")
            self.audit(session, ctx, "relay.demo.created", fixture["id"])
            self.authorize(session, ctx, "version:create")
            return {"fixture": fixture, "observation": observed, "source": source}

    def change_fixture(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:create")
            row, fixture = self.get(session, FixtureRow, ctx, identifier, True)
            if fixture["revision"] != body.expected_revision:
                raise InvalidStateTransitionError("Demo revision changed.")
            fixture.update(
                running=body.running,
                blocking_fault=body.blocking_fault,
                revision=fixture["revision"] + 1,
                updated_at=now(),
                last_execution_id=None,
            )
            self.put(session, ctx, row, fixture)
            observed, source = self.observation(session, ctx, fixture, "demo_change")
            self.audit(
                session,
                ctx,
                "relay.demo.changed",
                identifier,
                target_revision=fixture["revision"],
            )
            self.authorize(session, ctx, "version:create")
            return {"fixture": fixture, "observation": observed, "source": source}

    def signal(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "run:create")
            _, fixture = self.get(session, FixtureRow, ctx, body.target_id, True)
            existing = (
                session.query(IncidentRow)
                .filter_by(
                    organization_id=ctx.organization_id,
                    project_id=ctx.project_id,
                    dedup_key=body.dedup_key,
                )
                .first()
            )
            if existing:
                _, incident = self.get(session, IncidentRow, ctx, existing.id)
                if incident["target_id"] != fixture["id"]:
                    raise IdempotencyConflictError(
                        "Incident key belongs to a different disposable target."
                    )
                return incident
            if fixture["running"] and not fixture["blocking_fault"]:
                raise InvalidStateTransitionError(
                    "Healthy demo telemetry does not create a failure incident."
                )
            last = (
                session.query(ObservationRow)
                .filter_by(
                    target_id=fixture["id"],
                    organization_id=ctx.organization_id,
                    project_id=ctx.project_id,
                )
                .order_by(ObservationRow.created_at.desc(), ObservationRow.id.desc())
                .first()
            )
            if last is None:
                raise InvalidStateTransitionError(
                    "No verified demo telemetry observation exists."
                )
            _, observation = self.get(session, ObservationRow, ctx, last.id)
            if observation["target_revision"] != fixture["revision"]:
                raise InvalidStateTransitionError(
                    "Telemetry no longer describes the disposable target."
                )
            source = self.brief.ingest_in_session(
                session,
                ctx,
                {"kind": "demo_observation", "id": last.id},
                "Original disposable incident signal",
            )
            _, signal = self.add(
                session,
                ctx,
                SignalRow,
                Signal,
                "signal",
                **body.model_dump(),
                source_id=source["id"],
            )
            _, incident = self.add(
                session,
                ctx,
                IncidentRow,
                Incident,
                "incident",
                title="Disposable demo: " + fixture["name"],
                target_id=fixture["id"],
                signal_id=signal["id"],
                dedup_key=body.dedup_key,
                severity=body.severity,
                owner_id=ctx.actor.actor_id,
                status="OPEN",
                revision=1,
                updated_at=now(),
            )
            self.event(
                session, ctx, incident, "signal.received", reference_id=signal["id"]
            )
            self.authorize(session, ctx, "run:create")
            return incident

    def incident_for_mutation(self, session, ctx, identifier, revision=None):
        self.authorize(session, ctx, "run:create")
        _, initial = self.get(session, IncidentRow, ctx, identifier)
        target, fixture = self.get(session, FixtureRow, ctx, initial["target_id"], True)
        row, incident = self.get(session, IncidentRow, ctx, identifier, True)
        if revision is not None and incident["revision"] != revision:
            raise InvalidStateTransitionError(
                "Incident revision changed; review current evidence."
            )
        return row, incident, target, fixture

    def investigate(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            row, incident, _, fixture = self.incident_for_mutation(
                session, ctx, identifier, body.expected_revision
            )
            source_ids = body.source_ids
            if source_ids is None:
                observed = (
                    session.query(ObservationRow)
                    .filter_by(
                        target_id=fixture["id"],
                        organization_id=ctx.organization_id,
                        project_id=ctx.project_id,
                    )
                    .order_by(
                        ObservationRow.created_at.desc(), ObservationRow.id.desc()
                    )
                    .limit(2)
                    .all()
                )
                source_ids = [
                    self.brief.ingest_in_session(
                        session,
                        ctx,
                        {"kind": "demo_observation", "id": item.id},
                        "Read-only demo investigation",
                    )["id"]
                    for item in observed
                ]
            request = CreateBundle(
                title="Incident health evidence",
                source_ids=source_ids,
                hypothesis=Hypothesis(
                    question="Is the disposable demo service healthy?",
                    predicate="service_healthy",
                    minimum_sources=2,
                    target_id=fixture["id"],
                ),
            )
            bundle, evaluation = self.brief.bundle_in_session(session, ctx, request)
            self.brief.link(session, ctx, bundle["id"], "incident", identifier)
            try:
                self.grounding(session, ctx, bundle["id"], fixture)
                grounded = True
            except InvalidStateTransitionError:
                grounded = False
            _, investigation = self.add(
                session,
                ctx,
                InvestigationRow,
                Investigation,
                "investigation",
                incident_id=identifier,
                bundle_id=bundle["id"],
                diagnosis="LATEST_DEMO_TELEMETRY_UNHEALTHY" if grounded else "ABSTAIN",
                reason="Verified demo snapshots include conflicting health observations; no production root cause is inferred."
                if grounded
                else "Abstain: insufficient fresh verified evidence.",
            )
            incident["bundle_id"] = bundle["id"]
            self.transition(
                session,
                ctx,
                row,
                incident,
                "INVESTIGATING",
                "investigated",
                investigation["id"],
            )
            self.authorize(session, ctx, "run:create")
            return self.detail_in_session(session, ctx, identifier)

    def grounding(self, session, ctx, bundle_id, fixture):
        bundle = self.brief.bundle_detail_in_session(session, ctx, bundle_id)
        evaluation = bundle["evaluation"]
        if (
            bundle["hypothesis"]["predicate"] != "service_healthy"
            or bundle["hypothesis"]["target_id"] != fixture["id"]
            or evaluation["coverage"] < 2
            or evaluation["status"] not in {"CONFLICTING", "SUPPORTED"}
        ):
            raise InvalidStateTransitionError(
                "Abstention or incomplete evidence cannot authorize a recovery proposal."
            )
        matching = []
        for item in evaluation["items"]:
            if item["integrity"] != "VERIFIED" or item["freshness"] != "fresh":
                raise InvalidStateTransitionError(
                    "All proposal references must be fresh and verified."
                )
            _, data, _ = self.brief.source(session, ctx, item["source_id"])
            if (
                data.get("target_id") == fixture["id"]
                and data.get("target_revision") == fixture["revision"]
            ):
                matching.append(data)
        if (
            not matching
            or any(data.get("healthy") is not False for data in matching)
            or (fixture["running"] and not fixture["blocking_fault"])
        ):
            raise InvalidStateTransitionError(
                "Latest verified telemetry does not ground an unhealthy exact target revision."
            )
        return bundle

    def propose(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            row, incident, _, fixture = self.incident_for_mutation(
                session, ctx, identifier, body.expected_revision
            )
            if (
                body.target_id != fixture["id"]
                or body.target_revision != fixture["revision"]
                or body.bundle_id != incident["bundle_id"]
            ):
                raise InvalidStateTransitionError(
                    "Proposal target, revision or investigation bundle differs."
                )
            bundle = self.grounding(session, ctx, body.bundle_id, fixture)
            _, proposal = self.add(
                session,
                ctx,
                ProposalRow,
                ActionProposal,
                "proposal",
                incident_id=identifier,
                target_id=fixture["id"],
                target_revision=fixture["revision"],
                bundle_id=bundle["id"],
                bundle_digest=bundle["digest"],
                action=body.action,
                reason=self.clean(body.reason),
                payload_hash="0" * 64,
            )
            incident["proposal_id"] = proposal["id"]
            self.transition(
                session,
                ctx,
                row,
                incident,
                "PROPOSED",
                "proposal.created",
                proposal["id"],
            )
            self.authorize(session, ctx, "run:create")
            return self.detail_in_session(session, ctx, identifier)

    def current_proposal(self, session, ctx, incident, expected_hash):
        if incident["status"] != "PROPOSED" or not incident["proposal_id"]:
            raise InvalidStateTransitionError(
                "Incident has no current executable proposal."
            )
        _, proposal = self.get(session, ProposalRow, ctx, incident["proposal_id"])
        computed = digest(
            {key: value for key, value in proposal.items() if key != "payload_hash"}
        )
        if computed != proposal["payload_hash"] or expected_hash != computed:
            raise PayloadHashMismatchError(
                "The exact recovery proposal differs from the reviewed hash."
            )
        return proposal

    def approve(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:approve")
            _, incident, _, fixture = self.incident_for_mutation(
                session, ctx, identifier
            )
            proposal = self.current_proposal(session, ctx, incident, body.payload_hash)
            if fixture["revision"] != proposal["target_revision"]:
                raise InvalidStateTransitionError(
                    "Target changed since proposal review."
                )
            self.grounding(session, ctx, proposal["bundle_id"], fixture)
            approval = self.approvals.grant_approval(
                ctx,
                "relay_action",
                proposal["id"],
                proposal["payload_hash"],
                comments=self.clean(body.reason),
                session=session,
            )
            self.authorize(session, ctx, "version:approve")
            return approval.model_dump(mode="json")

    def execute(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            row, incident, _, fixture = self.incident_for_mutation(
                session, ctx, identifier
            )
            existing = (
                session.query(ExecutionRow)
                .filter_by(
                    organization_id=ctx.organization_id,
                    project_id=ctx.project_id,
                    idempotency_key=body.idempotency_key,
                )
                .first()
            )
            if existing:
                _, execution = self.get(session, ExecutionRow, ctx, existing.id)
                if (
                    execution["incident_id"],
                    execution["proposal_id"],
                    execution["payload_hash"],
                    execution["actor_id"],
                ) != (
                    identifier,
                    body.proposal_id,
                    body.payload_hash,
                    ctx.actor.actor_id,
                ):
                    raise IdempotencyConflictError(
                        "Recovery key belongs to a different immutable request."
                    )
                return self.detail_in_session(session, ctx, identifier)
            proposal = self.current_proposal(session, ctx, incident, body.payload_hash)
            if (
                proposal["id"] != body.proposal_id
                or fixture["revision"] != proposal["target_revision"]
            ):
                raise InvalidStateTransitionError(
                    "The current proposal or disposable target revision changed."
                )
            self.grounding(session, ctx, proposal["bundle_id"], fixture)
            approval = self.approvals.verify_approval(
                ctx,
                "relay_action",
                proposal["id"],
                proposal["payload_hash"],
                session=session,
            )
            self.core._fence()
            _, execution = self.add(
                session,
                ctx,
                ExecutionRow,
                RecoveryExecution,
                "recovery",
                incident_id=identifier,
                proposal_id=proposal["id"],
                payload_hash=proposal["payload_hash"],
                target_id=fixture["id"],
                owner_id=self.core.authority.owner_id,
                actor_id=ctx.actor.actor_id,
                idempotency_key=body.idempotency_key,
                approval={
                    key: getattr(approval, key)
                    for key in (
                        "approval_id",
                        "payload_hash",
                        "approved_by",
                        "created_at",
                    )
                },
                status="running",
                before_revision=fixture["revision"],
                before_snapshot={
                    key: fixture[key] for key in ("running", "blocking_fault")
                },
            )
            incident["execution_id"] = execution["id"]
            self.transition(
                session,
                ctx,
                row,
                incident,
                "EXECUTING",
                "action.claimed",
                execution["id"],
            )
            self.authorize(session, ctx, "run:create")
        # The durable claim is committed before the fixed effect; no blind retry.
        try:
            self.executor.apply(ctx, execution["id"])
            self.verify(ctx, identifier)
        except Exception as exc:
            from packages.contracts.core import Actor, ActorType, SecurityContext

            cleanup = SecurityContext(
                actor=Actor(
                    actor_id="system_recovery",
                    actor_type=ActorType.SYSTEM,
                    organization_id=ctx.organization_id,
                ),
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
            )
            with self.db.session(write=True) as session:
                self.core._fence()
                effect, saved = self._verified(
                    session, ExecutionRow, cleanup, execution["id"], True
                )
                row, incident = self._verified(
                    session, IncidentRow, cleanup, identifier, True
                )
                if saved["status"] in {"running", "action_completed"}:
                    denied = (
                        isinstance(
                            exc,
                            (
                                InvalidStateTransitionError,
                                PermissionDeniedError,
                                ApprovalRequiredError,
                                PayloadHashMismatchError,
                            ),
                        )
                        and saved["status"] == "running"
                    )
                    saved.update(
                        status="denied" if denied else "outcome_unknown",
                        error_code="effect_denied"
                        if denied
                        else "verification_requires_reconciliation",
                    )
                    self.put(session, cleanup, effect, saved)
                    self.transition(
                        session,
                        cleanup,
                        row,
                        incident,
                        "DEGRADED" if denied else "OUTCOME_UNKNOWN",
                        "action.unresolved",
                        execution["id"],
                    )
                    self.audit(
                        session,
                        cleanup,
                        "relay.effect.unresolved",
                        execution["id"],
                        error_type=type(exc).__name__,
                    )
        return self.detail(ctx, identifier)

    def verify(self, ctx, identifier, reconcile=False, expected_revision=None):
        with self.db.session(write=True) as session:
            if reconcile:
                self.authorize(session, ctx, "version:approve")
            row, incident, _, fixture = self.incident_for_mutation(
                session, ctx, identifier, expected_revision
            )
            effect, execution = self.get(
                session, ExecutionRow, ctx, incident["execution_id"], True
            )
            if not reconcile and (
                execution["owner_id"] != self.core.authority.owner_id
                or execution["status"] != "action_completed"
            ):
                raise ExecutionOwnershipError(
                    "Only the current completed fixed effect can be verified."
                )
            if reconcile and (
                incident["status"] != "OUTCOME_UNKNOWN"
                or execution["status"] != "outcome_unknown"
            ):
                raise InvalidStateTransitionError(
                    "Only an explicitly unresolved effect can be reconciled."
                )
            recovered = DemoHealthVerifier.observe(
                fixture, execution, allow_unexecuted=reconcile
            )
            observation, _ = self.observation(session, ctx, fixture, "verification")
            _, verification = self.add(
                session,
                ctx,
                VerificationRow,
                RecoveryVerification,
                "verification",
                incident_id=identifier,
                execution_id=execution["id"],
                target_id=fixture["id"],
                observation_id=observation["id"],
                target_revision=fixture["revision"],
                contract={
                    "kind": "demo_health_v1",
                    "require_running": True,
                    "require_no_blocking_fault": True,
                },
                recovered=recovered,
                digest="0" * 64,
            )
            execution.update(
                status="verified" if recovered else "health_failed",
                after_revision=fixture["revision"],
            )
            self.put(session, ctx, effect, execution)
            incident["verification_id"] = verification["id"]
            self.transition(
                session,
                ctx,
                row,
                incident,
                "RECOVERED" if recovered else "DEGRADED",
                "health.verified" if recovered else "health.failed",
                verification["id"],
            )
            self.authorize(
                session, ctx, "version:approve" if reconcile else "run:create"
            )

    def close(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            row, incident, _, fixture = self.incident_for_mutation(
                session, ctx, identifier, body.expected_revision
            )
            if incident["status"] != "RECOVERED" or not incident["verification_id"]:
                raise InvalidStateTransitionError(
                    "Only independently recovered incidents can close."
                )
            _, verification = self.get(
                session, VerificationRow, ctx, incident["verification_id"]
            )
            _, execution = self.get(
                session, ExecutionRow, ctx, incident["execution_id"]
            )
            if not verification["recovered"] or not DemoHealthVerifier.observe(
                fixture, execution
            ):
                raise InvalidStateTransitionError(
                    "Recovered health is no longer verified."
                )
            _, proposal = self.get(session, ProposalRow, ctx, incident["proposal_id"])
            _, capsule = self.add(
                session,
                ctx,
                CapsuleRow,
                IncidentCapsule,
                "capsule",
                incident_id=identifier,
                bundle_id=proposal["bundle_id"],
                bundle_digest=proposal["bundle_digest"],
                proposal_id=proposal["id"],
                proposal_hash=proposal["payload_hash"],
                verification_id=verification["id"],
                scenario_id="relay_demo_recovery",
                snapshot=execution["before_snapshot"],
                digest="0" * 64,
            )
            self.brief.link(
                session, ctx, capsule["bundle_id"], "capsule", capsule["id"]
            )
            incident["capsule_id"] = capsule["id"]
            self.transition(
                session, ctx, row, incident, "CLOSED", "incident.closed", capsule["id"]
            )
            self.authorize(session, ctx, "run:create")
            return self.detail_in_session(session, ctx, identifier)

    def detail_in_session(self, session, ctx, identifier):
        _, incident = self.get(session, IncidentRow, ctx, identifier)
        _, fixture = self.get(session, FixtureRow, ctx, incident["target_id"])
        _, signal = self.get(session, SignalRow, ctx, incident["signal_id"])
        timeline, _ = self.page(
            session, ctx, EventRow, limit=100, incident_id=identifier
        )
        details = {
            **incident,
            "fixture": fixture,
            "signal": signal,
            "timeline": sorted(timeline, key=lambda item: item["sequence"]),
        }
        for field, cls in (
            ("proposal", ProposalRow),
            ("execution", ExecutionRow),
            ("verification", VerificationRow),
            ("capsule", CapsuleRow),
        ):
            details[field] = (
                self.get(session, cls, ctx, incident[field + "_id"])[1]
                if incident[field + "_id"]
                else None
            )
        details["bundle"] = (
            self.brief.bundle_detail_in_session(session, ctx, incident["bundle_id"])
            if incident["bundle_id"]
            else None
        )
        details["approval"] = None
        if details["proposal"] and incident["status"] == "PROPOSED":
            try:
                record = self.approvals.verify_approval(
                    ctx,
                    "relay_action",
                    details["proposal"]["id"],
                    details["proposal"]["payload_hash"],
                    session=session,
                )
                details["approval"] = record.model_dump(mode="json")
            except Exception:
                pass  # Display cannot turn an absent/unverified receipt into authority.
        self.authorize(session, ctx)
        return details

    def detail(self, ctx, identifier):
        with self.db.session() as session:
            return self.detail_in_session(session, ctx, identifier)

    def recover(self):
        from packages.contracts.core import Actor, ActorType, SecurityContext

        self.core._fence()
        with self.db.session() as session:
            pending = (
                session.query(
                    ExecutionRow.id,
                    ExecutionRow.organization_id,
                    ExecutionRow.project_id,
                )
                .filter(ExecutionRow.status.in_(["running", "action_completed"]))
                .all()
            )
        for identifier, org, project in pending:
            ctx = SecurityContext(
                actor=Actor(
                    actor_id="system_recovery",
                    actor_type=ActorType.SYSTEM,
                    organization_id=org,
                ),
                organization_id=org,
                project_id=project,
            )
            with self.db.session(write=True) as session:
                row, execution = self._verified(
                    session, ExecutionRow, ctx, identifier, True
                )
                if execution["owner_id"] == self.core.authority.owner_id:
                    continue
                incident_row, incident = self._verified(
                    session, IncidentRow, ctx, execution["incident_id"], True
                )
                execution.update(
                    status="outcome_unknown",
                    error_code="restart_requires_reconciliation",
                )
                self.put(session, ctx, row, execution)
                self.transition(
                    session,
                    ctx,
                    incident_row,
                    incident,
                    "OUTCOME_UNKNOWN",
                    "execution.recovered",
                    identifier,
                )

    def capsule_in_session(self, session, ctx, identifier):
        from modules.core.history import HistoryUnverifiedError

        _, capsule = self.get(session, CapsuleRow, ctx, identifier)
        _, incident = self.get(session, IncidentRow, ctx, capsule["incident_id"])
        _, proposal = self.get(session, ProposalRow, ctx, capsule["proposal_id"])
        _, verification = self.get(
            session, VerificationRow, ctx, capsule["verification_id"]
        )
        _, execution = self.get(session, ExecutionRow, ctx, incident["execution_id"])
        bundle = self.brief.bundle_detail_in_session(session, ctx, capsule["bundle_id"])
        if (
            capsule["digest"]
            != digest({key: value for key, value in capsule.items() if key != "digest"})
            or incident["status"] != "CLOSED"
            or incident["capsule_id"] != identifier
            or proposal["payload_hash"] != capsule["proposal_hash"]
            or bundle["digest"] != capsule["bundle_digest"]
            or not verification["recovered"]
            or capsule["snapshot"] != execution["before_snapshot"]
            or any(
                item["integrity"] != "VERIFIED"
                for item in bundle["evaluation"]["items"]
            )
        ):
            raise HistoryUnverifiedError(
                "Capsule lineage or original evidence is unverified."
            )
        return capsule

    def capsule(self, ctx, identifier):
        with self.db.session() as session:
            return self.capsule_in_session(session, ctx, identifier)

    def inventory(self, ctx, after="", limit=25, q="", status=""):
        with self.db.session() as session:
            rows, cursor = self.page(session, ctx, IncidentRow, after, limit, q, status)
            return {"items": rows, "next": cursor}
