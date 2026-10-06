"""Human approval is bound to current, verified evidence and legal lifecycle state."""

import pytest
from sqlalchemy import text

from database.repositories.approval_repo import ApprovalRepository
from database.repositories.exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
)
from modules.bench.quality_gate import QualityGateFailedError
from modules.core.approvals.engine import ApprovalRequiredError
from packages.contracts.core import ActorType
from tests.conftest import bind_test_context


@pytest.mark.asyncio
async def test_unsigned_approval_cannot_publish(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        ApprovalRepository(s).record_approval(ctx, "forged", "agent_version", version.id,
                                             version.payload_hash, "owner")
        s.execute(text("UPDATE agent_versions SET status='approved' WHERE id=:id"), {"id": version.id})
    with pytest.raises(ApprovalRequiredError):
        factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
async def test_failed_reevaluation_requires_new_pass_and_new_human_decision(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    old = factory.approve_version(ctx, version.id)
    runtime.fail = True
    assert not (await factory.evaluate_version_with_bench(ctx, version.id)).passed
    with pytest.raises(QualityGateFailedError):
        factory.publish_version(ctx, version.id)
    runtime.fail = False
    latest = await factory.evaluate_version_with_bench(ctx, version.id)
    with pytest.raises(ApprovalRequiredError):
        factory.publish_version(ctx, version.id)
    new = factory.approve_version(ctx, version.id)
    assert new.approval_id != old.approval_id
    assert new.evaluation_id == latest.evaluation_id
    assert factory.publish_version(ctx, version.id).status.value == "published"
    with db.session() as s:
        assert s.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
async def test_engine_approval_does_not_bypass_factory_state_transition(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approval_engine.grant_approval(ctx, "agent_version", version.id, version.payload_hash)
    with pytest.raises(InvalidStateTransitionError):
        factory.publish_version(ctx, version.id)


def test_direct_engine_cannot_approve_nonexistent_agent(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    with pytest.raises(EntityNotFoundError):
        factory.approval_engine.grant_approval(ctx, "agent_version", "missing", version.payload_hash)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("approved_by", "agent-bot"), ("project_id", "another-project"),
    ("evaluation_id", "invented"), ("comments", "Altered decision"),
])
async def test_edited_approval_is_rejected(lifecycle, field, value):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    approval = factory.approve_version(ctx, version.id)
    with db.session() as s:
        s.execute(text(f"UPDATE approvals SET {field}=:value WHERE id=:id"),
                  {"value": value, "id": approval.approval_id})
    with pytest.raises(ApprovalRequiredError):
        factory.publish_version(ctx, version.id)


@pytest.mark.asyncio
async def test_system_actor_cannot_grant_human_approval(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    system_ctx = ctx.model_copy(deep=True)
    system_ctx.actor.actor_type = ActorType.SYSTEM
    bind_test_context(system_ctx)
    with pytest.raises(Exception, match="human|Human|human operators"):
        factory.approve_version(system_ctx, version.id)


@pytest.mark.asyncio
async def test_new_evaluation_logically_expires_old_approval(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    factory.approve_version(ctx, version.id)
    # Model a new legitimate evaluation cycle returning the version to draft.
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET status='draft' WHERE id=:id"), {"id": version.id})
    await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET status='approved' WHERE id=:id"), {"id": version.id})
    with pytest.raises(ApprovalRequiredError):
        factory.publish_version(ctx, version.id)
