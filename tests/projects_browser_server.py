"""Test-only Projects browser host: actual sessions/API/Core/DB, isolated inference.

Visual test content is not production data and does not prove live model availability.
"""
import os
import argparse
import secrets
import tempfile
from pathlib import Path
import uvicorn
from database.connection import DatabaseManager, create_db_engine
from services.api.studio import create_app, migrate, DEV_ACTOR, DEV_ORG
from packages.contracts.projects import ProjectInput
from tests.studio_runtime import IsolatedTestRuntime
from fastapi.testclient import TestClient
from tests.integration.test_studio_api import draft, promoted, PREFIX
from tests.integration.test_workflow_execution import graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--empty-role', choices=('admin', 'viewer'))
    parser.add_argument('--port', type=int, default=8873)
    args = parser.parse_args()
    os.environ['ARYN_ENV'] = 'development'
    os.environ['ARYN_AUTH_MODE'] = 'local-development'
    os.environ['ARYN_IDENTITY_SECRET'] = secrets.token_hex(32)
    os.environ['ARYN_EVIDENCE_SECRET'] = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix='aryn-projects-browser-') as directory:
        engine = create_db_engine('sqlite:///' + (Path(directory) / 'projects.sqlite3').as_posix())
        migrate(engine)
        db = DatabaseManager(engine)
        origin = f'http://127.0.0.1:{args.port}'
        if args.empty_role:
            from database.repositories.organization_repo import OrganizationRepository
            with db.session(write=True) as session:
                repo = OrganizationRepository(session)
                repo.create_organization(DEV_ORG, 'Empty browser organization', 'empty-browser')
                repo.add_member(DEV_ORG, DEV_ACTOR, args.empty_role)
            app = create_app(db, IsolatedTestRuntime(), origin=origin, testing=True)
            try:
                uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
            finally:
                engine.dispose()
            return
        app = create_app(db, IsolatedTestRuntime(), origin=origin, testing=True)
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, '')
        app.state.projects.save(ctx, ProjectInput(name='Validasi Proyek', description='Pekerjaan terisolasi untuk pengujian browser', idempotency_key='browser-project-seed'))
        # Only this test host creates governed sample resources. All writes go
        # through the actual API/Core lifecycle, with explicit isolated inference.
        with TestClient(app, base_url=origin, client=('127.0.0.1', 50000)) as client:
            session = client.post('/api/session', json={}, headers={'Origin': origin})
            client.headers.update({'Origin': origin, 'X-CSRF-Token': session.json()['csrf']})
            blueprint, version = draft(client)
            assignment = promoted(client, blueprint, version)
            definition = client.post(PREFIX + '/workflows', json={'name': 'Alur validasi hasil', 'graph': graph(assignment, version), 'expected_revision': 0})
            definition.raise_for_status()
            frozen = client.post(PREFIX + f"/workflows/{definition.json()['id']}/versions", json={'expected_revision': definition.json()['revision']})
            frozen.raise_for_status()
            started = client.post(PREFIX + f"/workflows/{definition.json()['id']}/runs", json={'version_id': frozen.json()['id'], 'input': 'Isolated project visual validation', 'idempotency_key': 'browser-output-validation', 'allow_remote_model': True})
            started.raise_for_status()
        try:
            uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
        finally:
            engine.dispose()


if __name__ == '__main__':
    main()
