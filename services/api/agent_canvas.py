"""Agent canvas API adapter. All editing/execution authority stays behind Core."""
from contextlib import asynccontextmanager

from modules.core.agent_preview import AgentPreviewService
from modules.core.errors import sanitize
from packages.contracts.agent_builder import AgentDraft, AgentPreviewInput, AgentPreviewView


def register_agent_canvas(app, coordinator, editor, context, model_catalog, require_runtime):
    preview = AgentPreviewService(coordinator, editor)
    app.state.agent_preview = preview
    prefix = "/api/projects/{project_id}"

    @app.get(prefix + "/factory/capabilities")
    async def capabilities(project_id: str):
        ctx = context(project_id)
        discovery = await model_catalog()
        ctx = context(project_id)
        models = discovery.models if discovery.discovery_valid else []
        inventory = await coordinator.runtime_adapter.runtime_inventory()
        ctx = context(project_id)
        default = AgentDraft(version_number="1.0.0", system_prompt="Jawab secara akurat. Nyatakan ketidakpastian dan batas bukti yang tersedia.",
            model=models[0]["model_id"], model_policy={"primary_model": models[0]["model_id"], "temperature": 0.3, "max_tokens": 2048}) if models else None
        return {"organization_id": ctx.organization_id, "project_id": project_id,
            "models": models, "draft_defaults": default.model_dump(mode="json") if default else None,
            "tools": [entry.approval.model_dump(mode="json") for key, entry in coordinator.mcp_tools._entries.items()
                if key[:2] == (ctx.organization_id, ctx.project_id) and entry.native],
            "skills": [skill.model_dump(mode="json") for skill in inventory.skills],
            "toolsets": [{"name": name, "tools": tools} for name, tools in (coordinator.mcp_tools.native_worker.toolsets.items()
                if coordinator.mcp_tools.native_worker is not None else [])
                if any(schema.get("x_hermes_toolset") == name for schema in coordinator.mcp_tools.native_worker.schemas.values())],
            "tool_policy": "core_registered_actions", "telemetry": "core_lifecycle_only"}

    @app.post(prefix + "/blueprints/{blueprint_id}/preview-runs", status_code=202, response_model=AgentPreviewView)
    async def start(project_id: str, blueprint_id: str, body: AgentPreviewInput):
        context(project_id, "run:create")
        await require_runtime()
        await model_catalog()
        result = preview.accept(context(project_id, "run:create"), blueprint_id, body)
        return clean(result)

    @app.get(prefix + "/blueprints/{blueprint_id}/preview-runs/{run_id}", response_model=AgentPreviewView)
    async def read(project_id: str, blueprint_id: str, run_id: str):
        return clean(preview.read(context(project_id), blueprint_id, run_id))

    def clean(result):
        return sanitize(result.model_dump(mode="json", exclude={"result": {"raw_response", "execution_evidence"}}),
            credentials=getattr(coordinator.db_manager, "protected_credentials", ()))

    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            try:
                yield
            finally:
                await preview.close()

    app.router.lifespan_context = lifespan
