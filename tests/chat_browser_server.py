"""Explicit offline browser fixture server. Never imported by product code.

Uses real API/Core/database/session contracts with a labelled isolated runtime.
This server is NOT evidence of model availability or live inference.
"""
import os
import secrets
import tempfile
from pathlib import Path

import uvicorn
from database.connection import DatabaseManager, create_db_engine
from database.repositories.organization_repo import OrganizationRepository
from services.api.studio import create_app, migrate, DEV_ACTOR, DEV_ORG
from tests.studio_runtime import IsolatedTestRuntime
from database.schema import ConversationModel
import asyncio


def main():
    os.environ["ARYN_ENV"] = "development"
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    os.environ["ARYN_IDENTITY_SECRET"] = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="aryn-chat-browser-") as directory:
        engine = create_db_engine("sqlite:///" + (Path(directory) / "chat.sqlite3").as_posix())
        migrate(engine)
        db = DatabaseManager(engine)
        runtime = IsolatedTestRuntime()
        original_turn = runtime.execute_direct_turn
        async def browser_turn(request, context):
            if context.project_id == "browser-crud-inflight":
                await asyncio.sleep(5)
            return await original_turn(request, context)
        runtime.execute_direct_turn = browser_turn
        app = create_app(db, runtime, origin="http://127.0.0.1:8871", testing=True)
        # Each browser case has a separate project; production rate limits stay intact.
        projects = [f"browser-{width}-{theme}" for width in (1920, 1440, 1024, 768, 390) for theme in ("dark", "light")]
        projects += ["browser-delivery", "browser-short-viewport", "browser-consent", "browser-scroll"]
        projects += [f"browser-crud-{width}-{theme}" for width in (1920, 1440, 1024, 768, 390) for theme in ("dark", "light")]
        projects += ["browser-crud-retry", "browser-crud-inactive", "browser-crud-inflight", "browser-crud-isolation", "browser-crud-keyboard"]
        with db.session(write=True) as session:
            repo = OrganizationRepository(session)
            for identifier in projects:
                ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, identifier)
                repo.create_project(ctx, identifier, "Chat browser testing", identifier)
            repo.add_member(DEV_ORG, "browser-other-user", role="admin")
            session.add(ConversationModel(id="chat_browser_other_user", organization_id=DEV_ORG,
                project_id="browser-crud-isolation", actor_id="browser-other-user", model="test/model-a",
                title="Private to another user", revision=0))
        try:
            uvicorn.run(app, host="127.0.0.1", port=8871, access_log=False)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
