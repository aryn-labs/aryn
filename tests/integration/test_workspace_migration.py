"""Forward additive migration preserves prior authority and guards data loss."""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from database.connection import create_db_engine


def revision(engine, target, *, downgrade=False):
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, target)


def test_workspace_migration_empty_roundtrip_and_populated_guard(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'migration.sqlite3'}")
    revision(engine, "015_authentication_boundary")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id,name,slug,created_at,updated_at) VALUES ('org','Org','org',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO projects (id,organization_id,name,slug,created_at,updated_at) VALUES ('project','org','Project','project',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    revision(engine, "head")
    assert "divisions" in inspect(engine).get_table_names()
    assert "ix_run_scope_created" in {index["name"] for index in inspect(engine).get_indexes("run_states")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM divisions")).scalar() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM projects")).scalar() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM approvals")).scalar() == 0
    revision(engine, "015_authentication_boundary", downgrade=True)
    assert "divisions" not in inspect(engine).get_table_names()
    revision(engine, "head")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO divisions (id,organization_id,project_id,name,slug,created_at,updated_at) VALUES ('division','org','project','Research','research',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    with pytest.raises(RuntimeError, match="populated workspace data"):
        revision(engine, "015_authentication_boundary", downgrade=True)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM divisions")).scalar() == "Research"
    engine.dispose()
