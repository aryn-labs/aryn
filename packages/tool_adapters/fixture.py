"""One deterministic fixture read; no host, credential, file or network handles.

This is explicitly an isolated verification tool, not a production data connector.
Authorization is exclusively the responsibility of the Core coordinator.
"""
from pydantic import BaseModel, ConfigDict, Field


class FixtureInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")


class FixtureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str
    text: str


NAME = "aryn_fixture_lookup"
CAPABILITY = "aryn.fixture.read"
RISK = "read_only_fixture"


def definition():
    return {"type": "function", "function": {"name": NAME,
        "description": "Read the isolated ARYN verification fixture by key (aryn-core).",
        "parameters": FixtureInput.model_json_schema()}}


def execute(arguments, context):
    import time
    from packages.contracts.runtime import ToolExecutionContext
    context = ToolExecutionContext.model_validate(context)
    if not context.run_id or not context.organization_id or not context.project_id or time.time() >= context.deadline_at:
        raise TimeoutError("Verified execution context has expired.")
    value = FixtureInput.model_validate(arguments)
    if value.key != "aryn-core":
        raise LookupError("Fixture unavailable.")
    return FixtureOutput(key=value.key, text="ARYN Core owns execution authorization.").model_dump()
