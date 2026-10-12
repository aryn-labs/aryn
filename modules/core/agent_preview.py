"""Text-only draft preview, claimed and metered by the existing Core coordinator.

Signed audit envelopes bind a preview to the captured working copy. No version,
assignment, publication, tool authority or parallel execution ledger is created.
"""
import asyncio
import hashlib
import json

from database.repositories.audit_repo import AuditRepository
from database.repositories.exceptions import EntityNotFoundError, InvalidStateTransitionError
from database.repositories.run_state_repo import RunStateRepository
from database.schema import AgentEditorLayoutModel, AuditEventModel
from modules.agent_factory.editor import EditorConflictError
from packages.contracts.agent_builder import AgentCanvasGraph, AgentDraft, AgentPreviewEvent, AgentPreviewView
from packages.contracts.core import AuditStatus
from packages.contracts.runtime import RunRequest


class AgentPreviewService:
    def __init__(self, coordinator, editor):
        self.core, self.editor = coordinator, editor
        self.db = coordinator.db_manager
        self.tasks = set()

    def accept(self, context, blueprint_id, body):
        with self.db.session(write=True) as session:
            self.editor.authorize(session, context, blueprint_id, True)
            record = self.editor.copy(session, context, blueprint_id)
            self.editor.check_generation(record, body)
            if not record.definition_json:
                raise InvalidStateTransitionError("Save the working copy first.")
            definition = AgentDraft.model_validate_json(record.definition_json)
            layout = session.query(AgentEditorLayoutModel).filter_by(
                blueprint_id=blueprint_id, actor_id=context.actor.actor_id,
                organization_id=context.organization_id, project_id=context.project_id,
            ).with_for_update().populate_existing().first()
            if not layout or layout.generation != body.expected_layout_generation:
                raise EditorConflictError("Canvas changed; reload before testing.")
            graph = AgentCanvasGraph.model_validate(json.loads(layout.layout_json).get("graph") or {})
            try:
                graph.require_preview_path()
            except ValueError:
                raise InvalidStateTransitionError("Connect Input → Agent → Output before testing.") from None
            definition_hash = hashlib.sha256(json.dumps(definition.model_dump(mode="json"),
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            reference = {"blueprint_id": blueprint_id, "working_copy_generation": record.generation,
                "definition_hash": definition_hash, "layout_generation": layout.generation}
            # The same bounded, text-only settings used by assigned execution. A
            # preview is diagnostic and does not establish Bench/output compliance.
            request = RunRequest(prompt=body.prompt, system_instructions=definition.system_prompt,
                model=definition.model, temperature=definition.temperature, max_tokens=definition.max_tokens,
                timeout_seconds=min(definition.budget_policy.timeout_seconds, definition.constraints.max_execution_time_seconds),
                max_total_tokens=definition.budget_policy.max_tokens_per_run,
                max_cost_usd=definition.budget_policy.max_cost_usd,
                idempotency_key=body.idempotency_key, metadata={"agent_preview": reference})
            owner, result = self.core._claim(request, context, "agent_preview", session=session)
            if owner:
                self.core.audit_logger.record("factory.preview.accepted", context, result.run_id,
                    AuditStatus.ALLOWED, reference, session=session)
        if owner:
            task = asyncio.create_task(self._execute(request, context, result))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return self.read(context, blueprint_id, result.run_id)

    async def _execute(self, request, context, result):
        try:
            await self.core.execute_managed_direct_turn(request, context, _claimed=(True, result))
        except BaseException as error:
            # Core normally persists its terminal outcome. Admission can be
            # revoked before entering dispatch; retain an honest unknown outcome.
            try:
                self.core._fail_dispatch(result.run_id, context, error)
            except Exception:
                pass

    def read(self, context, blueprint_id, run_id):
        with self.db.session() as session:
            self.editor.authorize(session, context, blueprint_id)
            run = RunStateRepository(session).get_run(context, run_id)
            if run.execution_mode != "agent_preview":
                raise EntityNotFoundError("Preview unavailable.")
            rows = session.query(AuditEventModel).filter_by(organization_id=context.organization_id,
                project_id=context.project_id, resource_id=run_id).order_by(AuditEventModel.occurred_at, AuditEventModel.id).limit(100).all()
            repo = AuditRepository(session)
            valid = [row for row in rows if repo.verify_authenticated_event(row)]
            accepted = next((row for row in valid if row.event_type == "factory.preview.accepted"), None)
            reference = json.loads(accepted.redacted_payload_json) if accepted else {}
            if reference.get("blueprint_id") != blueprint_id:
                raise EntityNotFoundError("Preview unavailable for this blueprint.")
            mapping = {"factory.preview.accepted": "input.accepted", "factory.preview.dispatched": "agent.dispatched",
                "core.run.completed": "run.completed", "core.run.failed": "run.failed",
                "core.run.outcome_unknown": "run.outcome_unknown", "core.run.recovered": "run.outcome_unknown",
                "core.run.cancelled": "run.cancelled", "core.run.cancellation.requested": "run.stopping"}
            events = [AgentPreviewEvent(id=row.id, sequence=index,
                occurred_at=AuditRepository.contract(row).occurred_at, type=mapping[row.event_type])
                for index, row in enumerate(valid) if row.event_type in mapping]
            self.editor.authorize(session, context, blueprint_id)
            return AgentPreviewView(organization_id=context.organization_id, project_id=context.project_id,
                blueprint_id=blueprint_id, working_copy_generation=reference["working_copy_generation"],
                definition_hash=reference["definition_hash"], input=run.prompt,
                result=self.core.stored_result(run), events=events)

    async def close(self):
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
