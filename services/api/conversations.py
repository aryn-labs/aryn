"""Authenticated Studio chat routes. Core owns scope, admission and execution."""
from contextlib import asynccontextmanager
from fastapi import Query
from fastapi.responses import JSONResponse
from modules.core.conversations import ChatError, Conversations
from packages.contracts.chat import ChatInput, ConsentInput, PreferenceInput


def register_conversations(app, coordinator, context, model_catalog, require_runtime):
    service = Conversations(coordinator, model_catalog, require_runtime)
    app.state.conversations = service
    prefix = "/api/projects/{project_id}/chat"

    @app.get(prefix + "/provider-consent")
    async def policies(project_id: str):
        return await service.settings.policies(context(project_id, "chat:read"))

    @app.post(prefix + "/provider-consent")
    async def grant(project_id: str, body: ConsentInput):
        return await service.settings.grant(context(project_id, "chat:create"), body)

    @app.delete(prefix + "/provider-consent/{provider_id}")
    def revoke(project_id: str, provider_id: str):
        return service.settings.revoke(context(project_id, "chat:read"), provider_id)

    @app.get(prefix + "/preferences")
    def preferences(project_id: str):
        return service.settings.preferences(context(project_id, "chat:read"))

    @app.patch(prefix + "/preferences")
    def preference(project_id: str, body: PreferenceInput):
        return service.settings.preferences(context(project_id, "chat:read"), body)

    @app.exception_handler(ChatError)
    async def error(request, exc):
        return JSONResponse({"error_code": exc.code, "message": "Chat request could not be completed."}, status_code=exc.status)

    @app.get(prefix + "/capability")
    async def capability(project_id: str):
        return await service.capability(context(project_id, "chat:read"))

    @app.get(prefix + "/conversations")
    def history(project_id: str, before: str | None = Query(None, max_length=64)):
        return service.history(context(project_id, "chat:read"), before)

    @app.get(prefix + "/conversations/{conversation_id}")
    def conversation(project_id: str, conversation_id: str):
        return service.read(context(project_id, "chat:read"), conversation_id)

    @app.post(prefix + "/conversations", status_code=202)
    async def start(project_id: str, body: ChatInput):
        return await service.accept(context(project_id, "chat:create"), body)

    @app.post(prefix + "/conversations/{conversation_id}/messages", status_code=202)
    async def send(project_id: str, conversation_id: str, body: ChatInput):
        return await service.accept(context(project_id, "chat:create"), body, conversation_id)

    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            try:
                yield
            finally:
                await service.close()

    app.router.lifespan_context = lifespan
