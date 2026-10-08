"""Integration tests against live Hermes Gateway on 127.0.0.1:8642."""

import os
import pytest
from tests.live_gateway import selected_live_model
from packages.contracts.core import Actor, SecurityContext
from packages.contracts.runtime import RunRequest, RunStatus

from packages.runtime_adapters.hermes import HermesRuntimeAdapter


def get_live_api_key() -> str:
    """Runtime auth must be supplied explicitly; no provider secret file reads."""
    return os.getenv("API_SERVER_KEY", "")

@pytest.mark.asyncio
async def test_live_hermes_health():
    api_key = get_live_api_key()
    if not api_key:
        pytest.skip("Hermes API_SERVER_KEY not found in local environment.")

    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key=api_key)
    health = await adapter.health()

    assert health.is_healthy is True
    assert health.platform == "hermes-agent"
    assert health.version and health.version != "unknown"


@pytest.mark.asyncio
async def test_live_hermes_capabilities_and_confinement():
    api_key = get_live_api_key()
    if not api_key:
        pytest.skip("Hermes API_SERVER_KEY not found in local environment.")

    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key=api_key)
    caps = await adapter.capabilities()

    # Invariant: Risky host access tools must NOT be active
    assert caps.tools_confined is True
    assert len(caps.details.get("active_risky_tools", [])) == 0
    assert len(caps.enabled_toolsets) == 0


@pytest.mark.asyncio
async def test_live_hermes_run_lifecycle_and_cancellation():
    api_key = get_live_api_key()
    if not api_key:
        pytest.skip("Hermes API_SERVER_KEY not found in local environment.")

    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key=api_key)
    actor = Actor(actor_id="test_runner", organization_id="org_aryn", project_id="proj_aryn")
    context = SecurityContext(actor=actor, organization_id="org_aryn", project_id="proj_aryn")

    live_model, _ = await selected_live_model(adapter)
    # 1. Start a run
    request = RunRequest(
        prompt="respond with the word ok",
        model=live_model,
    )
    run_id = await adapter.start_run(request, context)
    assert run_id.startswith("run_")

    # 2. Test cancel on the run
    cancelled = await adapter.cancel_run(run_id, context)
    assert cancelled is True

    # 3. Test get_result
    result = await adapter.get_result(run_id, context)
    assert result.run_id == run_id
    assert result.status in (RunStatus.STARTED, RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.STOPPING)
