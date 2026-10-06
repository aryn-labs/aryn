"""Automated security gate tests for Hermes Runtime Adapter.

Verifies:
- Loopback-only enforcement
- Authentication failure handling (HTTP 401)
- Request timeout handling
- Connection dropped / connection refused handling
- Tool confinement enforcement (blocking risky tools)
- Response schema validation
Complies with ARYN-SEC-001 and user task requirement 7.
"""

import importlib
import pytest
import httpx
from packages.contracts.core import Actor, SecurityContext
from packages.contracts.runtime import RunRequest

hermes_module = importlib.import_module("packages.runtime-adapters.hermes")
HermesRuntimeAdapter = hermes_module.HermesRuntimeAdapter
RuntimeSecurityError = hermes_module.RuntimeSecurityError
RuntimeAuthenticationError = hermes_module.RuntimeAuthenticationError
RuntimeTimeoutError = hermes_module.RuntimeTimeoutError
RuntimeConnectionError = hermes_module.RuntimeConnectionError
HermesAdapterError = hermes_module.HermesAdapterError


def test_adapter_rejects_non_loopback_urls():
    """Security Gate: Hermes adapter must refuse non-loopback addresses."""
    # Rejects public / remote IPs
    with pytest.raises(RuntimeSecurityError) as exc_info:
        HermesRuntimeAdapter(base_url="http://192.168.1.100:8642", api_key="dummy-key")
    assert "must bind only to loopback" in str(exc_info.value)

    with pytest.raises(RuntimeSecurityError) as exc_info2:
        HermesRuntimeAdapter(base_url="http://remote-server.com:8642", api_key="dummy-key")
    assert "must bind only to loopback" in str(exc_info2.value)

    # Accepts valid loopbacks
    adapter_ip = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key="dummy-key")
    assert adapter_ip.base_url == "http://127.0.0.1:8642"

    adapter_localhost = HermesRuntimeAdapter(base_url="http://localhost:8642", api_key="dummy-key")
    assert adapter_localhost.base_url == "http://localhost:8642"


@pytest.mark.asyncio
async def test_adapter_handles_authentication_failure():
    """Security Gate: 401 response from Hermes raises RuntimeAuthenticationError."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid gateway API key", "type": "gateway_auth_error"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key="wrong-key", http_client=client)

    with pytest.raises(RuntimeAuthenticationError):
        await adapter.capabilities()


@pytest.mark.asyncio
async def test_adapter_handles_timeout():
    """Security Gate: Timeouts raise typed RuntimeTimeoutError."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key="dummy-key", http_client=client)

    with pytest.raises(RuntimeTimeoutError):
        await adapter.health()


@pytest.mark.asyncio
async def test_adapter_handles_connection_refused():
    """Security Gate: Connection dropped / refused raises RuntimeConnectionError."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by peer", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key="dummy-key", http_client=client)

    with pytest.raises(RuntimeConnectionError):
        await adapter.health()


@pytest.mark.asyncio
async def test_adapter_blocks_run_when_tools_are_not_confined():
    """Security Gate: If Hermes reports risky tools enabled, adapter refuses start_run."""
    # Mocking Hermes reporting 'terminal' as enabled
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={
                "data": [
                    {"name": "terminal", "enabled": True},
                    {"name": "memory", "enabled": False}
                ]
            })
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    adapter = HermesRuntimeAdapter(base_url="http://127.0.0.1:8642", api_key="dummy-key", http_client=client)

    actor = Actor(actor_id="user_1", organization_id="org_1")
    context = SecurityContext(actor=actor, organization_id="org_1", project_id="proj_1")
    run_req = RunRequest(prompt="Test prompt", model="mock-model")

    with pytest.raises(RuntimeSecurityError) as exc_info:
        await adapter.start_run(run_req, context)

    assert "Risky tools active on Hermes API" in str(exc_info.value)
    assert "terminal" in str(exc_info.value)


@pytest.mark.asyncio
async def test_adapter_validates_malformed_run_response():
    """Security Gate: Malformed response from /v1/runs missing run_id raises HermesAdapterError."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.port == 20128 or request.url.path == "/aryn/gateway":
            from tests.gateway_fixtures import standard_handler
            return standard_handler(request, models=[{"id": "mock-model", "availability": "available"}])
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/v1/runs":
            return httpx.Response(200, json={"status": "started"})  # Missing run_id!
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    from tests.gateway_fixtures import make_adapter
    adapter = make_adapter(client)

    actor = Actor(actor_id="user_1", organization_id="org_1")
    context = SecurityContext(actor=actor, organization_id="org_1", project_id="proj_1")
    run_req = RunRequest(prompt="Test prompt", model="mock-model")

    with pytest.raises(HermesAdapterError) as exc_info:
        await adapter.start_run(run_req, context)

    assert "missing run_id" in str(exc_info.value)
