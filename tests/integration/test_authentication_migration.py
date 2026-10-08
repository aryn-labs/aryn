"""Authentication migration adds no authority or historical evidence."""
import io

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from database.connection import create_db_engine
from services.api.studio import ROOT


def test_authentication_upgrade_downgrade_preserves_governance(tmp_path, monkeypatch):
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'authentication.sqlite3').as_posix()}")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "014_execution_authority")
        connection.exec_driver_sql("INSERT INTO organizations (id,name,slug,created_at,updated_at) VALUES ('org','Original','original',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("SELECT name FROM organizations").scalar() == "Original"
        for table in ("external_identities", "auth_sessions", "login_transactions", "memberships", "agent_publications", "assignment_transitions", "audit_events"):
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM " + table).scalar() == 0
        command.downgrade(config, "014_execution_authority")
        assert "auth_sessions" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql("SELECT name FROM organizations").scalar() == "Original"
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
    monkeypatch.setenv("ARYN_DATABASE_URL", "postgresql://offline-placeholder/aryn")
    output = io.StringIO()
    offline = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    offline.set_main_option("script_location", str(ROOT / "database/migrations"))
    command.downgrade(offline, "015_authentication_boundary:014_execution_authority", sql=True)
    assert "DROP TABLE auth_sessions" in output.getvalue()
