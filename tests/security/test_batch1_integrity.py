"""Batch 1 negative gates, using real SQLite/Core/Bench and an isolated adapter."""

import json

import pytest
from sqlalchemy import text

from database.connection import DatabaseManager, create_db_engine
from database.repositories.agent_repo import AgentRepository
from database.repositories.organization_repo import OrganizationRepository
from database.schema import Base
from modules.agent_factory.service import AgentFactoryService
from modules.bench.runner import BenchRunner
from modules.core.workflows.coordinator import RunCoordinator
from packages.contracts.core import Actor, SecurityContext
from tests.conftest import bind_test_context
from tests.studio_runtime import IsolatedTestRuntime


@pytest.fixture
def lifecycle(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'batch.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    db = DatabaseManager(engine)
    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="owner", organization_id="org", roles=["admin"]),
        organization_id="org", project_id="project",
    ))
    with db.session() as s:
        repo = OrganizationRepository(s)
        repo.create_organization("org", "Test", "test")
        repo.add_member("org", "owner", "admin")
        repo.create_project(ctx, "project", "Test", "test")
    runtime = IsolatedTestRuntime()
    factory = AgentFactoryService(db, BenchRunner(runtime))
    bp = factory.create_blueprint(ctx, "Integrity", "integrity")
    version = factory.create_version(
        ctx, bp.id, "1.0.0", "Follow research safety guidelines.", "mock-fast",
        metadata={"security": {"tools": "denied"}},
    )
    yield db, ctx, runtime, factory, bp, version
    engine.dispose()


def test_hash_covers_security_metadata_and_exact_parameters(lifecycle):
    *_, version = lifecycle
    changed = version.model_copy(deep=True)
    changed.metadata["security"]["tools"] = "allowed"
    assert changed.calculate_payload_hash() != version.payload_hash
    reordered = version.model_copy(update={"metadata": {"security": {"tools": "denied"}}})
    assert reordered.calculate_payload_hash() == version.payload_hash
    changed = version.model_copy(update={"temperature": version.temperature + 0.00001})
    assert changed.calculate_payload_hash() != version.payload_hash


@pytest.mark.parametrize("column,value", [
    ("system_prompt", "Compromised prompt"), ("model", "mock-quality"),
    ("tool_grants_json", '["terminal"]'), ("temperature", 0.70001),
    ("max_tokens", 1024), ("metadata_json", '{"security":{"tools":"allowed"}}'),
])
@pytest.mark.asyncio
async def test_stored_configuration_tampering_is_rejected(lifecycle, column, value):
    db, ctx, runtime, factory, bp, version = lifecycle
    # Raw SQL models out-of-band corruption without changing the stored hash.
    with db.session() as s:
        s.execute(text(f"UPDATE agent_versions SET {column}=:value WHERE id=:id"),
                  {"value": value, "id": version.id})
    with pytest.raises(ValueError, match="integrity"):
        await factory.evaluate_version_with_bench(ctx, version.id)
    assert runtime.requests == []


@pytest.mark.asyncio
async def test_published_configuration_cannot_be_mutated_through_orm(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    factory.publish_version(ctx, version.id)
    with pytest.raises(ValueError, match="immutable"):
        with db.session() as s:
            AgentRepository(s).get_version(ctx, version.id).system_prompt = "Changed"
    with db.session() as s:
        stored = AgentRepository(s).get_version(ctx, version.id)
        assert stored.system_prompt == version.system_prompt
        assert json.loads(stored.metadata_json) == version.metadata


@pytest.mark.parametrize("stage", ["approve", "publish", "execute"])
@pytest.mark.asyncio
async def test_tampering_without_hash_change_blocks_all_lifecycle_gates(lifecycle, stage):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    if stage != "approve":
        factory.approve_version(ctx, version.id)
    if stage == "execute":
        factory.publish_version(ctx, version.id)
        assignment = factory.assign_agent(ctx, bp.id, version.id, "researcher")
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET system_prompt='Changed' WHERE id=:id"), {"id": version.id})
    before = len(runtime.requests)
    with pytest.raises(ValueError, match="integrity"):
        if stage == "approve":
            factory.approve_version(ctx, version.id)
        elif stage == "publish":
            factory.publish_version(ctx, version.id)
        else:
            await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Research", ctx)
    assert len(runtime.requests) == before
    with db.session() as s:
        assert s.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []
