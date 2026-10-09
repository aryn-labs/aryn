"""Divisions and read models with a disposable restricted PostgreSQL writer."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from sqlalchemy import text

from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.permissions.engine import PermissionEngine
from modules.core.workspace import WorkspaceService
from packages.contracts.workspace import DivisionInput, DivisionUpdate
from tests.postgresql.conftest import migrate_to

pytestmark = pytest.mark.postgresql


def test_live_division_generation_race_audit_scope_and_read_model(hosted_lifecycle):
    db, ctx, runtime, factory, *_ = hosted_lifecycle
    permissions = PermissionEngine(db_manager=db)
    service = WorkspaceService(db, permissions)
    created = service.save_division(ctx, DivisionInput(name="Research", slug="research"))
    barrier = threading.Barrier(2)
    def edit():
        barrier.wait(timeout=5)
        try:
            return service.save_division(ctx, DivisionUpdate(name="Evidence", slug="research", expected_generation=1), created["id"])["generation"]
        except InvalidStateTransitionError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [future.result(timeout=20) for future in [pool.submit(edit), pool.submit(edit)]]
    assert set(outcomes) == {2, "conflict"}
    from modules.core.workflows.coordinator import RunCoordinator
    from services.api.workspace_reads import WorkspaceReads
    reads = WorkspaceReads(db, permissions, RunCoordinator(runtime, db_manager=db, permission_engine=permissions))
    assert reads.summary(ctx)["metrics"]["divisions"]["value"] == 1
    detail = reads.detail(ctx, "divisions", created["id"])
    assert detail["generation"] == 2
    events = reads.page(ctx, "audits")["items"]
    assert len([event for event in events if event["name"].startswith("core.division.")]) == 2
    assert all(event["verified"] for event in events)
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar().startswith("aryn_writer_")


def test_live_workspace_populated_downgrade_guard(postgres_db, hosted_lifecycle):
    db, ctx, *_ = hosted_lifecycle
    service = WorkspaceService(db, PermissionEngine(db_manager=db))
    service.save_division(ctx, DivisionInput(name="Research", slug="research"))
    with pytest.raises(RuntimeError, match="populated workspace data"):
        migrate_to(postgres_db.owner, "015_authentication_boundary", downgrade=True)
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM divisions")).scalar() == 1
    with postgres_db.owner.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "017_agent_editor"
