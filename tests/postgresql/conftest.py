"""Disposable live databases: migration owner and restricted application writer.

Explicitly selecting this directory requires ARYN_TEST_POSTGRES_ADMIN_URL. It never
falls back to SQLite. The admin connection is for provisioning/attack tests only.
"""
import os
import secrets
import uuid
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from database.connection import DatabaseManager, create_db_engine
from database.governance_protection import HISTORY_TABLES, verify_hosted_writer
from database.workflow_protection import TABLES, MUTABLE_TABLES
from database.intelligence_protection import TABLES as INTELLIGENCE_TABLES, MUTABLE_TABLES as INTELLIGENCE_MUTABLE


def migrate_to(engine, revision, *, downgrade=False):
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, revision)


@dataclass
class HostedDatabase:
    db: DatabaseManager
    owner: object
    admin: object
    writer_name: str
    owner_name: str

    def grant_writer(self):
        with self.owner.begin() as connection:
            connection.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.writer_name}"'))
            connection.execute(text(f'REVOKE ALL ON alembic_version FROM "{self.writer_name}"'))
            for table in HISTORY_TABLES + TABLES + INTELLIGENCE_TABLES:
                connection.execute(text(f'REVOKE UPDATE, DELETE ON {table} FROM "{self.writer_name}"'))
            for table in MUTABLE_TABLES + INTELLIGENCE_MUTABLE:
                connection.execute(text(f'REVOKE DELETE ON {table} FROM "{self.writer_name}"'))
            connection.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.writer_name}"'))


@pytest.fixture
def postgres_db(tmp_path, monkeypatch):
    configured = os.getenv("ARYN_TEST_POSTGRES_ADMIN_URL")
    if not configured:
        pytest.fail("Live PostgreSQL requires ARYN_TEST_POSTGRES_ADMIN_URL; no SQLite fallback.")
    url = make_url(configured)
    assert url.get_backend_name() == "postgresql", "A real PostgreSQL connection is mandatory."
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    suffix = uuid.uuid4().hex[:16]
    database, owner_name, writer_name = [prefix + suffix for prefix in ("aryn_test_", "aryn_owner_", "aryn_writer_")]
    owner_password, writer_password = secrets.token_hex(32), secrets.token_hex(32)
    owner = writer = None
    try:
        with admin.connect() as connection:
            assert connection.execute(text("SELECT version()")).scalar().startswith("PostgreSQL ")
            connection.execute(text(f'CREATE ROLE "{owner_name}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD \'{owner_password}\''))
            connection.execute(text(f'CREATE ROLE "{writer_name}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD \'{writer_password}\''))
            connection.execute(text(f'CREATE DATABASE "{database}" OWNER "{owner_name}"'))
            connection.execute(text(f'REVOKE ALL ON DATABASE "{database}" FROM PUBLIC'))
            connection.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{writer_name}"'))
        owner = create_engine(url.set(database=database, username=owner_name, password=owner_password))
        migrate_to(owner, "head")
        with owner.begin() as connection:
            connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{writer_name}"'))
        writer = create_db_engine(url.set(database=database, username=writer_name, password=writer_password).render_as_string(hide_password=False))
        monkeypatch.setenv("ARYN_EVIDENCE_SECRET", secrets.token_hex(32))
        monkeypatch.setenv("ARYN_HISTORY_COMMITMENT_PATH", str(tmp_path / "protected-history.sqlite3"))
        hosted = HostedDatabase(DatabaseManager(writer), owner, admin, writer_name, owner_name)
        hosted.grant_writer()
        verify_hosted_writer(writer)
        with writer.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar() == writer_name
        yield hosted
    finally:
        if writer is not None:
            writer.dispose()
        if owner is not None:
            owner.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            connection.execute(text(f'DROP ROLE IF EXISTS "{writer_name}"'))
            connection.execute(text(f'DROP ROLE IF EXISTS "{owner_name}"'))
        admin.dispose()


@pytest.fixture
def hosted_lifecycle(postgres_db):
    from database.repositories.organization_repo import OrganizationRepository
    from modules.agent_factory.service import AgentFactoryService
    from modules.bench.runner import BenchRunner
    from packages.contracts.core import Actor, SecurityContext
    from tests.conftest import bind_test_context
    from tests.studio_runtime import IsolatedTestRuntime

    db = postgres_db.db
    ctx = bind_test_context(SecurityContext(actor=Actor(actor_id="owner", organization_id="org", roles=["admin"]),
                                          organization_id="org", project_id="project"))
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.create_organization("org", "PostgreSQL", "postgresql")
        repo.add_member("org", "owner", "admin")
        repo.create_project(ctx, "project", "Project", "project")
    runtime = IsolatedTestRuntime()
    factory = AgentFactoryService(db, BenchRunner(runtime))
    blueprint = factory.create_blueprint(ctx, "Integrity", "integrity")
    version = factory.create_version(ctx, blueprint.id, "1.0.0", "Follow research safety guidelines.", "mock-fast")
    return db, ctx, runtime, factory, blueprint, version
