"""Only for browser tests: isolated runtime + disposable DB + loopback port 8711."""

from pathlib import Path
from tempfile import mkdtemp

import uvicorn

from database.connection import DatabaseManager, create_db_engine, init_db
from services.api.studio import create_app
from tests.studio_runtime import IsolatedTestRuntime

if __name__ == "__main__":
    path = Path(mkdtemp(prefix="aryn-studio-browser-test-")) / "isolated.sqlite3"
    db = DatabaseManager(create_db_engine(f"sqlite:///{path.as_posix()}"))
    init_db(db.engine)
    app = create_app(
        db, IsolatedTestRuntime(), origin="http://127.0.0.1:8711", testing=True
    )
    uvicorn.run(app, host="127.0.0.1", port=8711, access_log=False)
