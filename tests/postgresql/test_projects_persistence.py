"""Disposable PostgreSQL, restricted writer and genuine Core project transactions."""
from tests.model_fixtures import offline_model_router

import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.permissions.engine import PermissionEngine
from modules.core.projects import ProjectService
from packages.contracts.projects import ProjectInput, ProjectUpdate
from modules.core.workflows.coordinator import RunCoordinator
from services.api.workspace_reads import WorkspaceReads
from services.api.project_reads import ProjectReads

pytestmark = pytest.mark.postgresql


def test_live_project_creation_edit_race_receipts_and_refresh(hosted_lifecycle):
    db, ctx, *_ = hosted_lifecycle
    permissions = PermissionEngine(db_manager=db)
    service = ProjectService(db, permissions)
    org_context = permissions.identity_binder.create_trusted_context(ctx.actor.actor_id, ctx.organization_id, '')
    payload = ProjectInput(name='PostgreSQL Project', description='Stored objective', idempotency_key=uuid.uuid4().hex)
    result = service.save(org_context, payload)
    assert service.save(org_context, payload) == result
    target = permissions.identity_binder.create_trusted_context(ctx.actor.actor_id, ctx.organization_id, result['id'])
    def edit(index):
        try:
            return service.save(target, ProjectUpdate(name=f'Edited Project {index}', description='Persistent', expected_generation=1, idempotency_key=uuid.uuid4().hex), result['id'])['generation']
        except InvalidStateTransitionError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(edit, (1, 2))) == {2, 'conflict'}
    with db.engine.connect() as connection:
        assert connection.execute(text('SELECT generation FROM projects WHERE id=:id'), {'id': result['id']}).scalar() == 2
        assert connection.execute(text('SELECT COUNT(*) FROM project_mutations WHERE project_id=:id'), {'id': result['id']}).scalar() == 2
    for operation in ('DELETE FROM project_mutations', "UPDATE project_mutations SET request_hash='forged'", 'TRUNCATE project_mutations'):
        with pytest.raises(DBAPIError):
            with db.engine.begin() as connection:
                connection.execute(text(operation))


@pytest.mark.asyncio
async def test_project_catalog_postgresql_queries_and_verified_bench(hosted_lifecycle):
    db, ctx, runtime, factory, _, version = hosted_lifecycle
    permissions = PermissionEngine(db_manager=db)
    coordinator = RunCoordinator(runtime, db_manager=db, permission_engine=permissions, model_router=offline_model_router())
    reads = ProjectReads(WorkspaceReads(db, permissions, coordinator))
    for collection in ('work', 'team', 'results', 'activity'):
        assert reads.page(ctx, collection)['project_id'] == ctx.project_id
    assert reads.page(ctx, 'work', active_only=True)['items'] == []
    evaluation = await factory.evaluate_version_with_bench(ctx, version.id)
    assert evaluation.passed
    results = reads.page(ctx, 'results', format='evaluation')['items']
    assert len(results) == 1 and results[0]['verified']
    assert reads.detail(ctx, 'evaluation', results[0]['id'])['references']['agent_version_id'] == version.id
