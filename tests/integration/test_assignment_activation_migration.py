"""AF-07 migration preserves historical artifacts without synthesizing receipts."""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from database.schema import Base
from services.api.studio import ROOT
from tests.integration.test_agent_registry_rollback import publications
from modules.core.workflows.coordinator import RunCoordinator
from modules.core.history import HistoryUnverifiedError


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["migrations"], indirect=True)
async def test_activation_upgrade_downgrade_keeps_versions_governance_and_existing_assignment(lifecycle):
    db, ctx, runtime, factory, bp, first, second, assignment, intent = await publications(lifecycle)
    run = await RunCoordinator(runtime, db_manager=db).execute_assigned_agent_turn(assignment.id, "Prior run", ctx, "migration-run-key")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with db.engine.begin() as connection:
        config.attributes["connection"] = connection
        columns = {table: ",".join(c["name"] for c in inspect(db.engine).get_columns(table) if c["name"] != "evaluation_owner_id") for table in ("agent_versions", "bench_evaluations", "bench_baselines", "bench_comparisons", "approvals")}
        records = {table: connection.exec_driver_sql(f"SELECT {columns[table]} FROM {table} ORDER BY id").all()
            for table in ("agent_versions", "bench_evaluations", "bench_baselines", "bench_comparisons", "approvals")}
        command.downgrade(config, "011_bench_baseline_regression")
        assert connection.exec_driver_sql("SELECT version_id FROM agent_assignments WHERE id=?", (assignment.id,)).scalar() == second.id
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM run_states WHERE execution_mode != 'bench'").scalar() == 1
        command.upgrade(config, "head")
        for table, before in records.items():
            assert connection.exec_driver_sql(f"SELECT {columns[table]} FROM {table} ORDER BY id").all() == before
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM agent_publications").scalar() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM assignment_transitions").scalar() == 0
        assert connection.exec_driver_sql("SELECT current_transition_id,activation_origin FROM agent_assignments WHERE id=?", (assignment.id,)).one() == (None, "legacy")
        assert connection.exec_driver_sql("SELECT agent_version_id,assignment_provenance_json FROM run_states WHERE id=?", (run.run_id,)).one() == (None, None)
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert all(not entry.rollback_eligible for entry in factory.version_registry(ctx, bp.id))
    intent = intent.model_copy(update={"expected_transition_id": None})
    with pytest.raises(HistoryUnverifiedError):
        factory.rollback_assignment(ctx, assignment.id, intent)
    assert factory.get_assignment(ctx, assignment.id).version_id == second.id
    for table in Base.metadata.sorted_tables:
        assert {c["name"] for c in inspect(db.engine).get_columns(table.name)} == set(table.columns.keys())
