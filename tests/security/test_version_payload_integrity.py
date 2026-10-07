"""Security integrity negative gates, using real SQLite/Core/Bench and an isolated adapter."""

import json

import pytest
from sqlalchemy import text

from database.repositories.agent_repo import AgentRepository
from modules.core.workflows.coordinator import RunCoordinator


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
    ("role", "compromised_role"),
    ("objective", "unauthorized objective"),
    ("output_contract_json", '{"format":"malicious"}'),
    ("constraints_json", '{"disallowed_actions":["compromised_action"]}'),
    ("tool_policy_json", '{"network_access":true}'),
    ("model_policy_json", '{"primary_model":"shadow_model"}'),
    ("budget_policy_json", '{"max_tokens_per_run":999999}'),
    ("evaluation_reference_json", '{"suite_id":"insecure_suite"}'),
    ("schema_version", "9.9.9"),
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
    with pytest.raises(ValueError, match="immutable"):
        with db.session() as s:
            AgentRepository(s).get_version(ctx, version.id).role = "ChangedRole"
    with pytest.raises(ValueError, match="immutable"):
        with db.session() as s:
            AgentRepository(s).get_version(ctx, version.id).output_contract_json = '{"format":"csv"}'
    with pytest.raises(ValueError, match="immutable"):
        with db.session() as s:
            AgentRepository(s).get_version(ctx, version.id).tool_policy_json = '{"network_access":true}'
    with db.session() as s:
        stored = AgentRepository(s).get_version(ctx, version.id)
        assert stored.system_prompt == version.system_prompt
        assert stored.role == version.role
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
    with db.session() as s:
        assert s.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.parametrize("column,value", [
    ("role", "compromised_role"),
    ("objective", "unauthorized objective"),
    ("output_contract_json", '{"format":"json"}'),
    ("constraints_json", '{"disallowed_actions":["compromised"]}'),
    ("tool_policy_json", '{"tool_grants":["terminal"]}'),
    ("model_policy_json", '{"primary_model":"shadow_model"}'),
    ("budget_policy_json", '{"max_tokens_per_run":999999}'),
    ("evaluation_reference_json", '{"suite_id":"other_suite"}'),
])
@pytest.mark.asyncio
async def test_legacy_hash_cannot_bypass_custom_definition_fields(lifecycle, column, value):
    db, ctx, runtime, factory, bp, version = lifecycle
    # Force the version row to have a legacy v2 hash
    legacy_hash = version.calculate_legacy_v2_payload_hash()
    with db.session() as s:
        s.execute(text(f"UPDATE agent_versions SET payload_hash=:hash, {column}=:value WHERE id=:id"),
                  {"hash": legacy_hash, "value": value, "id": version.id})

    # The row claims to match legacy hash, but has custom definition fields: must fail integrity!
    with pytest.raises(ValueError, match="integrity"):
        with db.session() as s:
            AgentRepository(s).get_version(ctx, version.id)


@pytest.mark.asyncio
async def test_unmodified_legacy_version_rejected_at_active_lifecycle_gates(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    clean_legacy_version = version.model_copy(update={"owner": None})
    legacy_hash = clean_legacy_version.calculate_legacy_v2_payload_hash()
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET payload_hash=:hash, owner=NULL WHERE id=:id"),
                  {"hash": legacy_hash, "id": version.id})

    # Evaluation with bench must reject legacy format
    with pytest.raises(Exception, match="legacy payload format"):
        await factory.evaluate_version_with_bench(ctx, version.id)

    # Approval must reject legacy format
    with pytest.raises(Exception, match="legacy payload format"):
        factory.approve_version(ctx, version.id)

    # Publication must reject legacy format
    with pytest.raises(Exception, match="legacy payload format"):
        factory.publish_version(ctx, version.id)
