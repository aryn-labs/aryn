"""Preserve legacy data while adding fail-closed evidence and execution claims."""

import io

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from database.connection import create_db_engine
from database.schema import Base
from services.api.studio import ROOT, migrate


def test_upgrade_from_005_retains_legacy_governance_and_run_data(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'migration.sqlite3').as_posix()}")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "005_bench_provenance")
        connection.exec_driver_sql("INSERT INTO organizations (id,name,slug,created_at,updated_at) VALUES ('org','Test','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO projects (id,organization_id,name,slug,created_at,updated_at) VALUES ('project','org','Test','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO approvals (id,organization_id,project_id,target_type,target_id,payload_hash,approved_by,status,created_at) VALUES ('legacy','org','project','agent_version','legacy','old','owner','approved',CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO run_states (id,organization_id,project_id,status,prompt,model,provider,input_tokens,output_tokens,total_tokens,created_at,updated_at) VALUES ('legacy','org','project','completed','Original','mock-fast','mock',1,2,3,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
    migrate(engine)
    with engine.connect() as connection:
        approval = connection.exec_driver_sql("SELECT payload_hash,evaluation_id,attestation FROM approvals WHERE id='legacy'").one()
        assert tuple(approval) == ("old", None, "")
        run = connection.exec_driver_sql("SELECT prompt,total_tokens,request_hash,runtime_run_id,execution_mode FROM run_states WHERE id='legacy'").one()
        assert tuple(run) == ("Original", 3, "", None, "legacy")
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        for table in ("external_identities", "auth_sessions", "login_transactions"):
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM " + table).scalar() == 0
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "020_core_automations"
        assert tuple(connection.exec_driver_sql("SELECT actual_model,gateway,runtime_backend,actual_provider FROM run_states WHERE id='legacy'").one()) == (None, None, None, None)
        assert any(index["unique"] and index["column_names"] == ["project_id", "idempotency_key"]
                   for index in inspect(engine).get_indexes("run_states"))
    for table in Base.metadata.sorted_tables:
        assert {c["name"] for c in inspect(engine).get_columns(table.name)} == set(table.columns.keys())
    engine.dispose()


def test_postgresql_migrations_compile_offline_without_cloud_connection(monkeypatch):
    monkeypatch.setenv("ARYN_DATABASE_URL", "postgresql://offline-placeholder/aryn")
    output = io.StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    command.upgrade(config, "head", sql=True)
    from alembic.script import ScriptDirectory
    assert len(ScriptDirectory.from_config(config).get_current_head()) <= 32
    sql = output.getvalue()
    assert "ADD COLUMN execution_attestation VARCHAR(64)" in sql
    assert "CREATE TABLE external_identities" in sql
    assert "CREATE TABLE auth_sessions" in sql
    assert "CREATE TABLE login_transactions" in sql
    assert "ADD COLUMN deadline_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ADD COLUMN reserved_tokens INTEGER" in sql
    assert "ADD COLUMN usage_availability VARCHAR(32)" in sql
    assert "ADD COLUMN attestation VARCHAR(64)" in sql
    assert "ADD COLUMN request_hash VARCHAR(64)" in sql
    assert "ADD COLUMN runtime_run_id VARCHAR(128)" in sql
    assert "ADD COLUMN actual_model VARCHAR(128)" in sql
    assert "ADD COLUMN output_contract_json TEXT" in sql
    assert "ADD COLUMN tool_policy_json TEXT" in sql
    assert "ADD COLUMN model_policy_json TEXT" in sql
    assert "CREATE UNIQUE INDEX uq_run_project_claim ON run_states (project_id, idempotency_key)" in sql
    assert "CREATE TABLE bench_baselines" in sql
    assert "CREATE TABLE bench_comparisons" in sql
    assert "uq_bench_baseline_generation" in sql
    assert "ADD COLUMN regression_comparison_id VARCHAR(64)" in sql
    assert "CREATE TABLE agent_publications" in sql
    assert "CREATE TABLE assignment_transitions" in sql
    assert "ADD COLUMN agent_payload_hash VARCHAR(64)" in sql
    assert "uq_assignment_transition_request" in sql
    assert "uq_assignment_transition_generation" in sql


def test_baseline_migration_upgrade_downgrade_preserves_existing_evaluations(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'bench-governance-migration.sqlite3').as_posix()}")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "010_agent_definition_contracts")
        connection.exec_driver_sql("INSERT INTO bench_evaluations (id,organization_id,project_id,blueprint_id,version_id,passed,total_scenarios,passed_scenarios,score,details_json,evaluated_by,evaluated_at,provenance_json) VALUES ('prior','org','project','bp','version',1,1,1,1,'[]','owner',CURRENT_TIMESTAMP,'{}')")
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("SELECT score,details_json,provenance_json FROM bench_evaluations WHERE id='prior'").one() == (1, "[]", "{}")
        command.downgrade(config, "010_agent_definition_contracts")
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM bench_evaluations").scalar() == 1
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["migrations"], indirect=True)
async def test_populated_baseline_history_downgrades_without_removing_evaluation_evidence(lifecycle, monkeypatch):
    from tests.integration.test_bench_baseline_regression import accepted, candidate
    db, ctx, runtime, factory, bp, version, prior, baseline = await accepted(lifecycle, monkeypatch)
    next_version = candidate(factory, ctx, bp)
    _current = await factory.evaluate_version_with_bench(ctx, next_version.id)
    factory.approve_version(ctx, next_version.id)
    factory.publish_version(ctx, next_version.id)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with db.engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM bench_baselines").scalar() == 2
        before = connection.exec_driver_sql("SELECT id,details_json,provenance_json FROM bench_evaluations ORDER BY id").all()
        config.attributes["connection"] = connection
        command.downgrade(config, "010_agent_definition_contracts")
        assert connection.exec_driver_sql("SELECT id,details_json,provenance_json FROM bench_evaluations ORDER BY id").all() == before
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM bench_baselines").scalar() == 0


def test_duplicate_legacy_keys_stop_upgrade_without_removing_runs(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'duplicate.sqlite3').as_posix()}")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "007_execution_claim")
        connection.exec_driver_sql("INSERT INTO organizations (id,name,slug,created_at,updated_at) VALUES ('org','Test','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO projects (id,organization_id,name,slug,created_at,updated_at) VALUES ('project','org','Test','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        for run_id in ("first", "second"):
            connection.exec_driver_sql("INSERT INTO run_states (id,organization_id,project_id,status,prompt,model,provider,input_tokens,output_tokens,total_tokens,idempotency_key,created_at,updated_at) VALUES (?,'org','project','queued','Legacy','mock-fast','mock',0,0,0,'duplicated',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", (run_id,))
    with pytest.raises(RuntimeError, match="duplikat"):
        migrate(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM run_states").scalar() == 2
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "007_execution_claim"
    engine.dispose()


def test_execution_migration_downgrade_upgrade_preserves_legacy_without_fabrication(tmp_path, monkeypatch):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'execution-migration.sqlite3').as_posix()}")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "013_history_integrity")
        connection.exec_driver_sql("INSERT INTO organizations (id,name,slug,created_at,updated_at) VALUES ('org','Test','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO projects (id,organization_id,name,slug,created_at,updated_at) VALUES ('project','org','Test','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.exec_driver_sql("INSERT INTO run_states (id,organization_id,project_id,status,prompt,model,provider,input_tokens,output_tokens,total_tokens,created_at,updated_at) VALUES ('legacy','org','project','completed','Preserve','mock-fast','mock',1,2,3,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("SELECT execution_claim_json,execution_attestation,execution_owner_id,deadline_at,usage_availability,total_tokens FROM run_states").one() == (None, None, None, None, "unavailable", 3)
        command.downgrade(config, "013_history_integrity")
        assert connection.exec_driver_sql("SELECT prompt,total_tokens FROM run_states").one() == ("Preserve", 3)
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM audit_events").scalar() == 0
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("SELECT execution_attestation,usage_availability FROM run_states").one() == (None, "unavailable")
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
    monkeypatch.setenv("ARYN_DATABASE_URL", "postgresql://offline-placeholder/aryn")
    output = io.StringIO()
    offline = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    offline.set_main_option("script_location", str(ROOT / "database/migrations"))
    command.downgrade(offline, "014_execution_authority:013_history_integrity", sql=True)
    assert "DROP COLUMN execution_attestation" in output.getvalue()
    assert "DROP COLUMN max_total_tokens" in output.getvalue()
