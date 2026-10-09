"""Durable sequential workflow execution under the existing Core authority.

Database blobs are the Local/Hosted storage adapters. Neither paths nor uploaded
HTML are accepted. Independent protected commitments detect state rollback.
"""

import datetime
import asyncio
import hashlib
import html
import json
import uuid

from database.schema import (
    WorkflowDefinitionModel as DefinitionRow,
    WorkflowVersionModel as VersionRow,
    WorkflowRunModel as RunRow,
    WorkflowArtifactModel as ArtifactRow,
    WorkflowDeliverableModel as DeliverableRow,
)
from database.repositories.agent_repo import AgentRepository
from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
)
from modules.core.history import advance_head, verify_head, HistoryUnverifiedError
from modules.core.permissions.engine import PermissionDeniedError
from modules.core.workflows.coordinator import IdempotencyConflictError
from modules.core.workflows.ownership import ExecutionOwnershipError
from modules.core.workflows.graph import validate_graph, reject
from modules.core.errors import sanitize
from packages.contracts.core import AuditStatus
from packages.contracts.workflow import (
    WorkflowDefinition,
    WorkflowVersion,
    WorkflowRun,
    TaskExecution,
    Artifact,
    Deliverable,
)


def encoded(payload):
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(payload):
    return hashlib.sha256(encoded(payload)).hexdigest()


def identity(prefix):
    return prefix + "_" + uuid.uuid4().hex


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


PREVIEW_CSP = "default-src 'none'; style-src 'none'; script-src 'none'; img-src 'none'; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; sandbox"


def render_document(text):
    # All model/user data is text, escaped even in downloads. No attributes,
    # resources, scripts, styles, forms or template expressions are interpolated.
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(PREVIEW_CSP, quote=True)}">'
        "<title>ARYN document preview</title></head><body><main><h1>Reviewed document</h1><pre>"
        + html.escape(text, quote=True)
        + "</pre></main></body></html>"
    ).encode()


class WorkflowExecutor:
    def __init__(self, coordinator):
        self.core = coordinator
        self.db = coordinator.db_manager
        self.permissions = coordinator.permission_engine

    def authorize(self, session, ctx, action="run:read"):
        self.permissions.enforce(
            action, ctx, ctx.organization_id, ctx.project_id, session=session
        )

    def get(self, session, cls, ctx, id, lock=False):
        query = session.query(cls).filter_by(
            id=id, organization_id=ctx.organization_id, project_id=ctx.project_id
        )
        row = (
            query.with_for_update().populate_existing().first()
            if lock
            else query.first()
        )
        if row is None:
            raise EntityNotFoundError("Workflow resource unavailable.")
        payload = json.loads(row.details_json)
        if (
            payload.get("id"),
            payload.get("organization_id"),
            payload.get("project_id"),
        ) != (row.id, row.organization_id, row.project_id):
            raise HistoryUnverifiedError("Workflow scope evidence differs.")
        if not self.db.evidence_signer.verify(
            row.__tablename__, payload, row.attestation
        ):
            raise HistoryUnverifiedError("Workflow signature differs.")
        for field in (
            "status",
            "workflow_id",
            "version_id",
            "workflow_run_id",
            "artifact_id",
            "revision",
        ):
            if (
                field in payload
                and getattr(row, field, payload[field]) != payload[field]
            ):
                raise HistoryUnverifiedError("Workflow relationship evidence differs.")
        verify_head(session, row.__tablename__, ctx, id, {"digest": digest(payload)})
        return row, payload

    def put(self, session, ctx, row, payload, new=False):
        if isinstance(row, RunRow):
            row.status = payload["status"]
        expected = None if new else {"digest": digest(json.loads(row.details_json))}
        advance_head(
            session,
            row.__tablename__,
            ctx,
            row.id,
            expected,
            {"digest": digest(payload)},
        )
        row.details_json = encoded(payload).decode()
        row.attestation = self.db.evidence_signer.sign(row.__tablename__, payload)
        if new:
            session.add(row)
        session.flush()

    def scoped(self, cls, ctx, id, **kwargs):
        return cls(
            id=id,
            organization_id=ctx.organization_id,
            project_id=ctx.project_id,
            **kwargs,
        )

    def audit(self, session, ctx, event, subject, **details):
        self.core.audit_logger.record(
            "workflow." + event,
            ctx,
            subject,
            AuditStatus.COMPLETED,
            details,
            session=session,
        )

    def draft(self, ctx, body, id=None):
        with self.db.session(write=True) as s:
            self.authorize(s, ctx, "version:create")
            if id:
                row, prior = self.get(s, DefinitionRow, ctx, id, True)
                if (
                    body.expected_revision != row.revision
                    or prior["revision"] != row.revision
                ):
                    raise InvalidStateTransitionError(
                        "Draft revision changed; reload and restore input."
                    )
                revision = row.revision + 1
            else:
                if body.expected_revision != 0:
                    raise InvalidStateTransitionError(
                        "New definition starts at revision zero."
                    )
                id, revision = identity("workflow"), 1
                row = self.scoped(DefinitionRow, ctx, id, revision=revision)
            definition = WorkflowDefinition.model_validate(
                body.model_dump(exclude={"expected_revision"})
            )
            ids = {n.id for n in definition.graph.nodes}
            if len({p.id for p in definition.positions}) != len(
                definition.positions
            ) or any(p.id not in ids for p in definition.positions):
                reject("layout", "invalid_layout_identity")
            payload = {
                "id": id,
                "organization_id": ctx.organization_id,
                "project_id": ctx.project_id,
                "revision": revision,
                **definition.model_dump(mode="json"),
            }
            row.revision = revision
            self.put(s, ctx, row, payload, new=id is not None and revision == 1)
            self.audit(s, ctx, "draft.saved", id, revision=revision)
            self.authorize(s, ctx, "version:create")
            return payload

    def pinned(self, s, ctx, graph):
        validate_graph(graph)
        repo = AgentRepository(s)
        activation = AgentActivationRepository(
            s, self.db.evidence_signer, self.permissions
        )
        for node in graph.nodes:
            if node.kind != "agent" or node.renderer:
                continue
            try:
                assignment = activation.lock_assignment(ctx, node.assignment_id)
                if (
                    assignment.status != "active"
                    or assignment.version_id != node.agent_version_id
                ):
                    reject(node.id, "assignment_pin_changed")
                version = repo.get_version(ctx, node.agent_version_id)
                if json.loads(version.tool_grants_json):
                    reject(node.id, "tools_forbidden")
                history = activation.history(ctx, assignment)
                reference = activation.known_good(ctx, version.id)
                if not history or history[-1].publication_reference != reference:
                    reject(node.id, "unverified_assignment")
            except EntityNotFoundError:
                reject(node.id, "pinned_resource_unavailable")

    def validate(self, ctx, id):
        with self.db.session(write=True) as s:
            self.authorize(s, ctx, "version:create")
            _, draft = self.get(s, DefinitionRow, ctx, id, True)
            graph = WorkflowDefinition.model_validate(
                {k: draft[k] for k in ("name", "graph", "positions")}
            ).graph
            self.pinned(s, ctx, graph)
            return {
                "valid": True,
                "digest": digest(graph.model_dump(mode="json")),
                "revision": draft["revision"],
            }

    def freeze(self, ctx, id, body):
        with self.db.session(write=True) as s:
            self.authorize(s, ctx, "version:publish")
            row, draft = self.get(s, DefinitionRow, ctx, id, True)
            if (
                body.expected_revision != draft["revision"]
                or row.revision != draft["revision"]
            ):
                raise InvalidStateTransitionError(
                    "Reload changed draft before freezing."
                )
            graph = WorkflowDefinition.model_validate(
                {k: draft[k] for k in ("name", "graph", "positions")}
            ).graph
            self.pinned(s, ctx, graph)
            old = (
                s.query(VersionRow)
                .filter_by(workflow_id=id, revision=row.revision)
                .first()
            )
            if old:
                return self.get(s, VersionRow, ctx, old.id)[1]
            version = WorkflowVersion(
                id=identity("workflow_version"),
                workflow_id=id,
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                revision=row.revision,
                graph=graph,
                digest=digest(graph.model_dump(mode="json")),
            )
            self.put(
                s,
                ctx,
                self.scoped(
                    VersionRow, ctx, version.id, workflow_id=id, revision=row.revision
                ),
                version.model_dump(mode="json"),
                True,
            )
            self.audit(s, ctx, "version.frozen", version.id, digest=version.digest)
            self.authorize(s, ctx, "version:publish")
            return version.model_dump(mode="json")

    def version(self, s, ctx, id):
        row, payload = self.get(s, VersionRow, ctx, id)
        version = WorkflowVersion.model_validate(payload)
        if row.workflow_id != version.workflow_id or version.digest != digest(
            version.graph.model_dump(mode="json")
        ):
            raise HistoryUnverifiedError("Immutable workflow graph differs.")
        return version

    def fence(self, run):
        self.core._fence()
        if run.owner_id != self.core.authority.owner_id:
            raise ExecutionOwnershipError("Stale workflow owner is fenced.")

    async def start(self, ctx, workflow_id, body, *, claim_callback=None, automation_reference=None, max_task_tokens=None):
        self.core._fence()
        with self.db.session(write=True) as s:
            self.authorize(s, ctx, "run:create")
            self.get(s, DefinitionRow, ctx, workflow_id, True)
            fingerprint = digest(
                {
                    "workflow_id": workflow_id,
                    "version_id": body.version_id,
                    "input": body.input,
                    "actor_id": ctx.actor.actor_id,
                }
            )
            old = (
                s.query(RunRow)
                .filter_by(
                    organization_id=ctx.organization_id,
                    project_id=ctx.project_id,
                    idempotency_key=body.idempotency_key,
                )
                .first()
            )
            if old:
                _, payload = self.get(s, RunRow, ctx, old.id)
                if payload["request_hash"] != fingerprint:
                    raise IdempotencyConflictError(
                        "Workflow key belongs to another input/actor/version."
                    )
                return payload
            version = self.version(s, ctx, body.version_id)
            if version.workflow_id != workflow_id:
                reject("graph", "wrong_workflow_version")
            self.pinned(s, ctx, version.graph)
            start, _ = validate_graph(version.graph)
            run = WorkflowRun(
                id=identity("workflow_run"),
                workflow_id=workflow_id,
                version_id=version.id,
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                actor_id=ctx.actor.actor_id,
                owner_id=self.core.authority.owner_id,
                status="running",
                cursor=start,
                input=body.input,
                request_hash=fingerprint,
                automation_reference=automation_reference,
                max_task_tokens=max_task_tokens,
                tasks=[
                    TaskExecution(node_id=n.id, status="pending")
                    for n in version.graph.nodes
                ],
            )
            self.put(
                s,
                ctx,
                self.scoped(
                    RunRow,
                    ctx,
                    run.id,
                    workflow_id=workflow_id,
                    version_id=version.id,
                    idempotency_key=body.idempotency_key,
                ),
                run.model_dump(mode="json"),
                True,
            )
            self.audit(s, ctx, "run.started", run.id, version_id=version.id)
            if claim_callback is not None:
                claim_callback(s, run)
        return await self.execute(ctx, run.id)

    def artifact(self, s, ctx, id):
        row, payload = self.get(s, ArtifactRow, ctx, id)
        item = Artifact.model_validate(payload)
        blob = bytes(row.blob)
        if (
            row.workflow_run_id != item.workflow_run_id
            or len(blob) != item.length
            or hashlib.sha256(blob).hexdigest() != item.digest
        ):
            raise HistoryUnverifiedError("Artifact integrity failed.")
        if item.mime != (
            "text/html" if item.schema_name == "website" else "application/json"
        ):
            raise HistoryUnverifiedError("Artifact MIME differs from schema.")
        if item.mime == "text/html":
            # Reconstruct allowlisted template to detect a compromised renderer.
            if not item.source_artifact_id:
                raise HistoryUnverifiedError("Staging source missing.")
            source, source_blob = self.artifact(s, ctx, item.source_artifact_id)
            if source.schema_name != "content" or blob != render_document(
                json.loads(source_blob)["text"]
            ):
                raise HistoryUnverifiedError("Staging isolation template differs.")
        else:
            envelope = json.loads(blob)
            if (
                set(envelope) != {"text", "schema"}
                or envelope["schema"] != item.schema_name
                or not isinstance(envelope["text"], str)
            ):
                raise HistoryUnverifiedError("Artifact envelope differs.")
        return item, blob

    def store_artifact(self, s, ctx, run, node, text, result=None):
        blob = (
            render_document(text)
            if node.renderer
            else encoded({"text": sanitize(text), "schema": node.output_schema})
        )
        if not 0 < len(blob) <= 65536:
            raise InvalidStateTransitionError("Artifact exceeds the 64 KiB limit.")
        item = Artifact(
            id=identity("artifact"),
            organization_id=ctx.organization_id,
            project_id=ctx.project_id,
            workflow_run_id=run.id,
            task_id=node.id,
            schema_name=node.output_schema,
            mime="text/html" if node.renderer else "application/json",
            digest=hashlib.sha256(blob).hexdigest(),
            length=len(blob),
            source_artifact_id=run.artifact_id,
            core_run_id=result.run_id if result else None,
            agent_version_id=result.agent_version_id if result else None,
            model=result.actual_model if result else None,
            created_at=now(),
            validation="inert-static-document" if node.renderer else "text-envelope",
        )
        row = self.scoped(ArtifactRow, ctx, item.id, workflow_run_id=run.id, blob=blob)
        self.put(s, ctx, row, item.model_dump(mode="json"), True)
        # Check the actual rendered bytes before committing artifact/event.
        self.artifact(s, ctx, item.id)
        self.audit(
            s,
            ctx,
            "artifact.created",
            item.id,
            digest=item.digest,
            task_id=node.id,
            core_run_id=item.core_run_id,
        )
        return item.id

    async def execute(self, ctx, id):
        while True:
            with self.db.session(write=True) as s:
                self.authorize(s, ctx, "run:create")
                row, payload = self.get(s, RunRow, ctx, id, True)
                run = WorkflowRun.model_validate(payload)
                self.fence(run)
                if run.status != "running":
                    return payload
                version = self.version(s, ctx, run.version_id)
                nodes = {n.id: n for n in version.graph.nodes}
                node = nodes[run.cursor]
                task = next(t for t in run.tasks if t.node_id == node.id)
                if task.status != "pending":
                    raise InvalidStateTransitionError(
                        "Task already claimed; replay forbidden."
                    )
                text = run.input
                if node.kind != "start":
                    try:
                        if not run.artifact_id:
                            raise InvalidStateTransitionError(
                                "Required artifact handoff is missing."
                            )
                        artifact, blob = self.artifact(s, ctx, run.artifact_id)
                        if (
                            artifact.workflow_run_id != id
                            or artifact.schema_name != node.input_schema
                        ):
                            raise InvalidStateTransitionError(
                                "Artifact handoff has wrong lineage/schema."
                            )
                        text = (
                            json.loads(blob)["text"]
                            if artifact.mime == "application/json"
                            else ""
                        )
                        task.input_artifact_id = artifact.id
                    except (
                        HistoryUnverifiedError,
                        InvalidStateTransitionError,
                        EntityNotFoundError,
                        ValueError,
                        KeyError,
                    ):
                        run.status, task.status, run.error_code = (
                            "failed",
                            "failed",
                            "handoff_rejected",
                        )
                        self.put(s, ctx, row, run.model_dump(mode="json"))
                        self.audit(s, ctx, "handoff.rejected", id, node_id=node.id)
                        return run.model_dump(mode="json")
                if node.kind == "review":
                    task.status = "waiting_review"
                    run.status = "waiting_review"
                    for untouched in run.tasks:
                        if (
                            untouched.status == "pending"
                            and nodes[untouched.node_id].kind != "end"
                        ):
                            untouched.status = "skipped"
                    self.put(s, ctx, row, run.model_dump(mode="json"))
                    self.audit(
                        s, ctx, "review.waiting", id, artifact_id=run.artifact_id
                    )
                    return run.model_dump(mode="json")
                task.status = "running"
                self.put(s, ctx, row, run.model_dump(mode="json"))
                self.audit(s, ctx, "task.claimed", id, node_id=node.id)
            # No transaction or row lock spans model inference.
            result = None
            try:
                if node.kind == "agent" and not node.renderer:

                    def capture(session, claimed, node_id=node.id):
                        current, saved = self.get(session, RunRow, ctx, id, True)
                        active = WorkflowRun.model_validate(saved)
                        self.fence(active)
                        if active.status != "running" or active.cursor != node_id:
                            raise InvalidStateTransitionError(
                                "Workflow claim no longer dispatchable."
                            )
                        next(
                            t for t in active.tasks if t.node_id == node_id
                        ).core_run_id = claimed.run_id
                        self.put(session, ctx, current, active.model_dump(mode="json"))

                    result = await self.core.execute_assigned_agent_turn(
                        node.assignment_id,
                        text,
                        ctx,
                        "workflow:" + id + ":" + node.id,
                        expected_version_id=node.agent_version_id,
                        claim_callback=capture,
                        automation_reference=run.automation_reference,
                        max_total_tokens=run.max_task_tokens,
                        workflow_reference={
                            "workflow_id": run.workflow_id,
                            "run_id": id,
                            "node_id": node.id,
                        },
                    )
                    if (
                        result.status.value != "completed"
                        or not result.execution_claim_verified
                        or not result.assignment_provenance_verified
                    ):
                        raise InvalidStateTransitionError(
                            "Core task did not complete with verified evidence."
                        )
                    text = result.output
                with self.db.session(write=True) as s:
                    self.authorize(s, ctx, "run:create")
                    row, payload = self.get(s, RunRow, ctx, id, True)
                    run = WorkflowRun.model_validate(payload)
                    self.fence(run)
                    task = next(t for t in run.tasks if t.node_id == node.id)
                    if (
                        run.status != "running"
                        or run.cursor != node.id
                        or task.status != "running"
                    ):
                        return payload  # Cancellation can win; late result cannot create an artifact.
                    if node.kind in {"start", "agent"}:
                        run.artifact_id = self.store_artifact(
                            s, ctx, run, node, text, result
                        )
                    task.output_artifact_id = run.artifact_id
                    task.status = "completed"
                    _, outgoing = validate_graph(version.graph)
                    port = (
                        ("yes" if node.predicate.matches(text) else "no")
                        if node.kind == "condition"
                        else "value"
                    )
                    run.cursor = next(
                        e.target for e in outgoing[node.id] if e.source_port == port
                    )
                    self.put(s, ctx, row, run.model_dump(mode="json"))
                    self.audit(
                        s,
                        ctx,
                        "task.completed",
                        id,
                        node_id=node.id,
                        artifact_id=run.artifact_id,
                    )
            except ExecutionOwnershipError:
                raise
            except (Exception, asyncio.CancelledError) as exc:
                with self.db.session(write=True) as s:
                    row, payload = self.get(s, RunRow, ctx, id, True)
                    run = WorkflowRun.model_validate(payload)
                    self.fence(run)
                    if run.status == "running":
                        task = next(t for t in run.tasks if t.node_id == node.id)
                        run.status = (
                            "outcome_unknown"
                            if task.core_run_id
                            and (
                                result is None
                                or result.status.value == "outcome_unknown"
                            )
                            else "failed"
                        )
                        task.status = run.status
                        run.error_code = (
                            "core_outcome_unknown"
                            if run.status == "outcome_unknown"
                            else "task_rejected"
                        )
                        self.put(s, ctx, row, run.model_dump(mode="json"))
                        self.audit(
                            s,
                            ctx,
                            "task.failed",
                            id,
                            node_id=node.id,
                            error_code=run.error_code,
                        )
                # Core already persisted sanitized failure; never expose exception text.
                if isinstance(exc, (PermissionDeniedError, asyncio.CancelledError)):
                    raise
                return run.model_dump(mode="json")

    def review(self, ctx, id, body):
        with self.db.session(write=True) as s:
            self.authorize(s, ctx, "version:approve")
            self.core._fence()
            row, payload = self.get(s, RunRow, ctx, id, True)
            run = WorkflowRun.model_validate(payload)
            artifact, _ = self.artifact(s, ctx, run.artifact_id)
            if artifact.digest != body.digest:
                raise InvalidStateTransitionError(
                    "Review digest changed; reload exact artifact."
                )
            old = s.query(DeliverableRow).filter_by(workflow_run_id=id).first()
            if old:
                _, decision = self.get(s, DeliverableRow, ctx, old.id)
                if (decision["reviewer"], decision["decision"], decision["reason"]) != (
                    ctx.actor.actor_id,
                    body.decision,
                    body.reason,
                ):
                    raise IdempotencyConflictError(
                        "Review already committed differently."
                    )
                return decision
            if run.status != "waiting_review":
                raise InvalidStateTransitionError("Workflow is not waiting for review.")
            decision = Deliverable(
                id=identity("deliverable"),
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                workflow_run_id=id,
                artifact_id=artifact.id,
                digest=artifact.digest,
                reviewer=ctx.actor.actor_id,
                decision=body.decision,
                reason=sanitize(body.reason),
                created_at=now(),
            )
            self.put(
                s,
                ctx,
                self.scoped(
                    DeliverableRow,
                    ctx,
                    decision.id,
                    workflow_run_id=id,
                    artifact_id=artifact.id,
                ),
                decision.model_dump(mode="json"),
                True,
            )
            run.owner_id = self.core.authority.owner_id
            run.status = "completed" if body.decision == "accepted" else "rejected"
            for task in run.tasks:
                if task.status == "waiting_review":
                    task.status = "completed"
                elif task.status == "pending":
                    task.status = (
                        "completed" if body.decision == "accepted" else "skipped"
                    )
                    task.input_artifact_id = artifact.id
                    task.output_artifact_id = (
                        artifact.id if body.decision == "accepted" else None
                    )
            self.put(s, ctx, row, run.model_dump(mode="json"))
            self.authorize(s, ctx, "version:approve")
            self.audit(
                s,
                ctx,
                "review." + body.decision,
                decision.id,
                digest=decision.digest,
                artifact_id=artifact.id,
            )
            return decision.model_dump(mode="json")

    async def cancel(self, ctx, id):
        with self.db.session(write=True) as s:
            self.authorize(s, ctx, "run:cancel")
            row, payload = self.get(s, RunRow, ctx, id, True)
            run = WorkflowRun.model_validate(payload)
            if run.status == "waiting_review":
                self.core._fence()
                run.owner_id = self.core.authority.owner_id
            else:
                self.fence(run)
            if run.status not in {"running", "waiting_review"}:
                return payload
            task = next(t for t in run.tasks if t.node_id == run.cursor)
            core_id = task.core_run_id if task.status == "running" else None
            run.status = "outcome_unknown" if core_id else "cancelled"
            run.error_code = "stop_unconfirmed" if core_id else None
            task.status = run.status
            for pending in run.tasks:
                if pending.status == "pending":
                    pending.status = "cancelled"
            self.put(s, ctx, row, run.model_dump(mode="json"))
            self.audit(
                s, ctx, "run.stop_requested", id, core_run_id=core_id, status=run.status
            )
        if core_id:
            await self.core.cancel_managed_run(core_id, ctx)
        return run.model_dump(mode="json")

    def recover(self):
        self.core._fence()
        with self.db.session() as s:
            rows = (
                s.query(RunRow.id, RunRow.organization_id, RunRow.project_id)
                .filter_by(status="running")
                .all()
            )
        for id, org, project in rows:
            from packages.contracts.core import Actor, ActorType, SecurityContext

            ctx = SecurityContext(
                actor=Actor(
                    actor_id="system_recovery",
                    actor_type=ActorType.SYSTEM,
                    organization_id=org,
                ),
                organization_id=org,
                project_id=project,
            )
            with self.db.session(write=True) as s:
                row, payload = self.get(s, RunRow, ctx, id, True)
                run = WorkflowRun.model_validate(payload)
                if (
                    run.status == "running"
                    and run.owner_id != self.core.authority.owner_id
                ):
                    run.status = "outcome_unknown"
                    run.error_code = "restart_requires_reconciliation"
                    for task in run.tasks:
                        if task.status == "running":
                            task.status = "outcome_unknown"
                    self.put(s, ctx, row, run.model_dump(mode="json"))
                    self.audit(s, ctx, "run.recovered", id, status=run.status)

    def read(self, ctx, cls, id):
        with self.db.session() as s:
            self.authorize(s, ctx)
            _, payload = self.get(s, cls, ctx, id)
            if cls is VersionRow:
                payload = self.version(s, ctx, id).model_dump(mode="json")
            if cls is RunRow:
                version = self.version(s, ctx, payload["version_id"])
                payload = {**payload, "graph_digest": version.digest}
            if cls is ArtifactRow:
                item, _ = self.artifact(s, ctx, id)
                consumers = s.query(RunRow).filter_by(id=item.workflow_run_id).first()
                _, run = self.get(s, RunRow, ctx, consumers.id)
                payload = {
                    **payload,
                    "consumers": [
                        t["node_id"]
                        for t in run["tasks"]
                        if t["input_artifact_id"] == id
                    ],
                }
            self.authorize(s, ctx)
            return payload

    def inventory(self, ctx, cls, after="", limit=25, workflow_id=None, waiting=False):
        with self.db.session() as s:
            self.authorize(s, ctx)
            query = s.query(cls).filter_by(
                organization_id=ctx.organization_id, project_id=ctx.project_id
            )
            if workflow_id:
                self.get(s, DefinitionRow, ctx, workflow_id)
                query = query.filter_by(workflow_id=workflow_id)
            from sqlalchemy import or_, and_

            if waiting:
                query = query.filter_by(status="waiting_review")
            if after:
                cursor, _ = self.get(s, cls, ctx, after)
                if workflow_id and cursor.workflow_id != workflow_id:
                    raise EntityNotFoundError("Pagination scope differs.")
                query = query.filter(
                    or_(
                        cls.created_at < cursor.created_at,
                        and_(cls.created_at == cursor.created_at, cls.id < cursor.id),
                    )
                )
            rows = (
                query.order_by(cls.created_at.desc(), cls.id.desc())
                .limit(limit + 1)
                .all()
            )
            items = []
            for row in rows[:limit]:
                _, payload = self.get(s, cls, ctx, row.id)
                items.append(
                    {
                        k: v
                        for k, v in payload.items()
                        if k not in {"graph", "positions", "input", "tasks"}
                    }
                )
            self.authorize(s, ctx)
            return {
                "items": items,
                "next": rows[limit - 1].id if len(rows) > limit else None,
            }

    def download(self, ctx, id):
        with self.db.session() as s:
            self.authorize(s, ctx)
            artifact, blob = self.artifact(s, ctx, id)
            self.authorize(s, ctx)
            return artifact, blob
