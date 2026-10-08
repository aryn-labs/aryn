"""Only for browser tests: isolated runtime + disposable DB + loopback port 8711."""

from pathlib import Path
import os
from tempfile import mkdtemp

import uvicorn

from database.connection import DatabaseManager, create_db_engine, init_db
from services.api.studio import create_app, DEV_ACTOR, DEV_ORG, DEV_PROJECT
from database.repositories.organization_repo import OrganizationRepository
from tests.studio_runtime import IsolatedTestRuntime

if __name__ == "__main__":
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    path = Path(mkdtemp(prefix="aryn-studio-browser-test-")) / "isolated.sqlite3"
    db = DatabaseManager(create_db_engine(f"sqlite:///{path.as_posix()}"))
    init_db(db.engine)
    app = create_app(
        db, IsolatedTestRuntime(), origin="http://127.0.0.1:8711", testing=True
    )
    # Second real, empty project only in the disposable browser-test database.
    # Exercise project switching through scoped API snapshots without projecting metrics.
    with db.session(write=True) as session:
        context = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
        repo = OrganizationRepository(session)
        repo.create_project(context, "proj_studio_browser_secondary", "Proyek Uji Kedua", "browser-secondary")
        repo.add_project_member("proj_studio_browser_secondary", DEV_ACTOR)
    uvicorn.run(app, host="127.0.0.1", port=8711, access_log=False)
