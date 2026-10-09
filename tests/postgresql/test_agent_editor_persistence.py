from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from sqlalchemy import text

from database.repositories.exceptions import InvalidStateTransitionError, DuplicateEntityError
from database.schema import AgentVersionModel
from modules.agent_factory.editor import AgentEditor
from packages.contracts.agent import AgentVersion
from packages.contracts.agent_builder import AgentDraft, WorkingCopyInput, GenerationInput, LayoutInput
from tests.postgresql.conftest import migrate_to

pytestmark = pytest.mark.postgresql


def test_live_editor_generation_race_candidate_atomicity_and_hash(hosted_lifecycle):
    db, ctx, _, factory, blueprint, version = hosted_lifecycle
    editor = AgentEditor(factory)
    definition = AgentDraft(version_number="1.1.0", system_prompt=version.system_prompt, model=version.model,
        temperature=version.temperature, max_tokens=version.max_tokens, owner=ctx.actor.actor_id,
        metadata={"purpose": "research"}, model_policy={"primary_model": version.model,
            "temperature": version.temperature, "max_tokens": version.max_tokens})
    body = WorkingCopyInput(expected_generation=0, definition=definition)
    barrier = threading.Barrier(2)
    def save():
        barrier.wait(timeout=5)
        try:
            return editor.save(ctx, blueprint.id, body).generation
        except InvalidStateTransitionError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(save), pool.submit(save)]]
    assert set(results) == {1, "conflict"}
    editor.layout(ctx, blueprint.id, LayoutInput(expected_generation=0, positions=[{"id": "model", "x": 321, "y": 120}]))
    assert editor.layout(ctx, blueprint.id).positions[0].x == 321
    candidate = editor.candidate(ctx, blueprint.id, GenerationInput(expected_generation=1))
    assert candidate.metadata == {"purpose": "research"}
    with db.session() as session:
        assert session.query(AgentVersionModel).count() == 2
        assert session.get(AgentVersionModel, version.id).payload_hash == version.payload_hash
        AgentVersion.from_stored(session.get(AgentVersionModel, candidate.id)).verify_integrity(require_canonical=True)
    with pytest.raises(DuplicateEntityError, match="already exists"):
        editor.candidate(ctx, blueprint.id, GenerationInput(expected_generation=1))
    with db.session() as session:
        assert session.query(AgentVersionModel).count() == 2
        assert session.execute(text("SELECT COUNT(*) FROM audit_events WHERE event_type='factory.version.created'")).scalar() == 2


def test_live_editor_populated_downgrade_guard(postgres_db, hosted_lifecycle):
    db, ctx, _, factory, blueprint, _ = hosted_lifecycle
    AgentEditor(factory).layout(ctx, blueprint.id, LayoutInput(expected_generation=0, positions=[]))
    with pytest.raises(RuntimeError, match="stored drafts/layout"):
        migrate_to(postgres_db.owner, "016_workspace_structure", downgrade=True)
    with postgres_db.owner.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "020_core_automations"
        assert connection.execute(text("SELECT COUNT(*) FROM agent_editor_layouts")).scalar() == 1
