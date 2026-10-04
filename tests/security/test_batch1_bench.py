"""Bench evidence cannot be promoted by inserting or editing PASS records."""

import json

import pytest
from sqlalchemy import text

from database.connection import DatabaseManager
from database.repositories.bench_repo import BenchRepository
from modules.agent_factory.service import AgentFactoryService
from modules.bench.quality_gate import QualityGateFailedError
from modules.bench.runner import BenchRunner
from modules.bench.scenarios import get_standard_research_bench_scenarios
from packages.contracts.bench import BenchEvaluationResult
from tests.studio_runtime import IsolatedTestRuntime


def test_inserting_fabricated_pass_is_rejected(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    forged = BenchEvaluationResult(
        evaluation_id="forged", blueprint_id=bp.id, version_id=version.id,
        passed=True, total_scenarios=4, passed_scenarios=4, score=1,
        requested_model=version.model, payload_hash=version.payload_hash,
    )
    with pytest.raises(QualityGateFailedError):
        with db.session() as s:
            BenchRepository(s).record_evaluation(ctx, forged)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("score", 0.25), ("total_scenarios", 0), ("passed_scenarios", 0),
    ("details_json", "[]"), ("provenance_json", "{}"),
])
async def test_edited_evidence_is_not_eligible(lifecycle, field, value):
    db, ctx, runtime, factory, bp, version = lifecycle
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        s.execute(text(f"UPDATE bench_evaluations SET {field}=:value WHERE id=:id"),
                  {"value": value, "id": result.evaluation_id})
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)


@pytest.mark.asyncio
async def test_empty_suite_cannot_be_used_for_publication(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    with pytest.raises(QualityGateFailedError):
        await factory.evaluate_version_with_bench(ctx, version.id, scenarios=[])
    assert runtime.requests == []


@pytest.mark.asyncio
async def test_valid_attestation_survives_database_manager_restart(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    restarted = AgentFactoryService(DatabaseManager(db.engine), BenchRunner(IsolatedTestRuntime()))
    assert restarted.approve_version(ctx, version.id).payload_hash == version.payload_hash
    with db.session() as s:
        assert s.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.asyncio
async def test_changed_suite_and_duplicate_scenarios_rejected_before_dispatch(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    scenarios = get_standard_research_bench_scenarios()
    scenarios[1] = scenarios[0]
    with pytest.raises(QualityGateFailedError):
        await factory.evaluate_version_with_bench(ctx, version.id, scenarios)
    assert runtime.requests == []


@pytest.mark.asyncio
async def test_latest_real_failure_invalidates_previous_real_pass(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    await factory.evaluate_version_with_bench(ctx, version.id)
    runtime.fail = True
    failed = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not failed.passed
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)


@pytest.mark.asyncio
async def test_actual_model_mismatch_fails_bench(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    execute = runtime.execute_direct_turn
    async def wrong_model(request, context):
        result = await execute(request, context)
        result.model = "different-model"
        return result
    runtime.execute_direct_turn = wrong_model
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    assert not result.passed and result.passed_scenarios == 0
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)


@pytest.mark.asyncio
async def test_fabricating_outputs_and_scores_without_attestation_is_rejected(lifecycle):
    db, ctx, runtime, factory, bp, version = lifecycle
    result = await factory.evaluate_version_with_bench(ctx, version.id)
    with db.session() as s:
        record = BenchRepository(s).get_evaluation(ctx, result.evaluation_id)
        details = json.loads(record.details_json)
        details[0]["actual_output"] = "I cannot comply; different fabricated evidence"
        record.details_json = json.dumps(details)
    with pytest.raises(QualityGateFailedError):
        factory.approve_version(ctx, version.id)
