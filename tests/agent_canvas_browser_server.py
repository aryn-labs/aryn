"""Disposable browser host. Core/API/DB are real; inference is an explicit test double.

The event barrier observes an actual Core dispatch before releasing the isolated
runtime. It never introduces simulated production canvas stages.
"""
import asyncio
import os
import tempfile
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from database.connection import DatabaseManager, create_db_engine
from packages.contracts.projects import ProjectInput
from services.api.studio import create_app, migrate, DEV_ACTOR, DEV_ORG
from tests.integration.test_studio_api import draft, promoted
from tests.studio_runtime import IsolatedTestRuntime


class CanvasTestRuntime(IsolatedTestRuntime):
    def __init__(self):
        super().__init__()
        self.gate = None

    async def execute_direct_turn(self, request, context):
        if self.gate is not None:
            await self.gate.wait()
        return await super().execute_direct_turn(request, context)


def main():
    os.environ["ARYN_ENV"] = "development"
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    with tempfile.TemporaryDirectory(prefix="aryn-agent-canvas-") as directory:
        engine = create_db_engine("sqlite:///" + (Path(directory) / "canvas.sqlite3").as_posix())
        migrate(engine)
        runtime = CanvasTestRuntime()
        app = create_app(DatabaseManager(engine), runtime, origin="http://127.0.0.1:8874", testing=True)
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "")
        app.state.projects.save(ctx, ProjectInput(name="Validasi Kanvas", description="Database disposable pengujian canvas", idempotency_key="canvas-project-seed"))
        with TestClient(app, base_url="http://127.0.0.1:8874", client=("127.0.0.1", 50000)) as client:
            response = client.post("/api/session", json={}, headers={"Origin": "http://127.0.0.1:8874"})
            client.headers.update({"Origin": "http://127.0.0.1:8874", "X-CSRF-Token": response.json()["csrf"]})
            bp, version = draft(client)
            promoted(client, bp, version)

        @app.post("/__test__/runtime-gate")
        async def gate(body: dict):
            if body.get("hold"):
                runtime.gate = asyncio.Event()
            elif runtime.gate:
                runtime.gate.set()
                runtime.gate = None
            return {"isolated_test_only": True}

        try:
            uvicorn.run(app, host="127.0.0.1", port=8874, access_log=False)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
