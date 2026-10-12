"""Workflow browser evidence host: real API/Core, migrated disposable DB, isolated inference."""
import asyncio
import os
import tempfile
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from database.connection import DatabaseManager, create_db_engine
from packages.contracts.projects import ProjectInput
from services.api.studio import create_app, migrate, DEV_ACTOR, DEV_ORG
from tests.agent_canvas_browser_server import CanvasTestRuntime
from tests.integration.test_studio_api import draft, promoted


def main():
    os.environ["ARYN_ENV"] = "development"
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    with tempfile.TemporaryDirectory(prefix="aryn-workflow-browser-") as directory:
        engine = create_db_engine("sqlite:///" + (Path(directory) / "workflow.sqlite3").as_posix())
        migrate(engine)
        try:
            runtime = CanvasTestRuntime()
            origin = "http://127.0.0.1:8876"
            app = create_app(DatabaseManager(engine), runtime, origin=origin, testing=True)
            ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "")
            app.state.projects.save(ctx, ProjectInput(name="Proyek Workflow Kosong", description="Database disposable workflow", idempotency_key="workflow-project-seed"))
            with TestClient(app, base_url=origin, client=("127.0.0.1", 50000)) as client:
                response = client.post("/api/session", json={}, headers={"Origin": origin})
                client.headers.update({"Origin": origin, "X-CSRF-Token": response.json()["csrf"]})
                for slug in ("workflow-agent-a", "workflow-agent-b"):
                    blueprint, version = draft(client, slug)
                    promoted(client, blueprint, version, role_name=slug)

            @app.post("/__test__/runtime-gate")
            async def gate(body: dict):
                if body.get("hold"):
                    runtime.gate = asyncio.Event()
                elif runtime.gate:
                    runtime.gate.set()
                    runtime.gate = None
                return {"isolated_test_only": True}
            uvicorn.run(app, host="127.0.0.1", port=8876, access_log=False)
        finally:
            engine.dispose()



if __name__ == "__main__":
    main()
