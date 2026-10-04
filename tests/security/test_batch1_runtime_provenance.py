"""Transport doubles verify Hermes evidence without contacting any live model."""

import copy

import httpx
import pytest

from packages.contracts.core import Actor, SecurityContext
from packages.contracts.runtime import RunRequest
from packages.runtime_adapters import HermesAdapterError, HermesRuntimeAdapter

RESPONSE = {
    "id": "actual-runtime-id", "model": "mock-fast",
    "choices": [{"message": {"content": "Isolated output"}}],
    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["id", "model", "usage", None])
async def test_direct_response_requires_actual_provenance(missing):
    response = copy.deepcopy(RESPONSE)
    if missing:
        response.pop(missing)
    def handler(request):
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json=response)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = HermesRuntimeAdapter(api_key="isolated-transport-test", http_client=client)
        ctx = SecurityContext(actor=Actor(actor_id="test", organization_id="org"), organization_id="org", project_id="project")
        if missing:
            with pytest.raises(HermesAdapterError):
                await adapter.execute_direct_turn(RunRequest(prompt="Test", model="mock-fast"), ctx)
        else:
            result = await adapter.execute_direct_turn(RunRequest(prompt="Test", model="mock-fast"), ctx)
            assert result.run_id == "actual-runtime-id" and result.model == "mock-fast"
            assert result.usage.total_tokens == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("capabilities", [{}, {"data": [{"name": "terminal"}]}, {"data": "unknown"}])
async def test_malformed_capabilities_cannot_claim_tool_confinement(capabilities):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=capabilities))) as client:
        adapter = HermesRuntimeAdapter(api_key="isolated-transport-test", http_client=client)
        with pytest.raises(HermesAdapterError):
            await adapter.capabilities()
