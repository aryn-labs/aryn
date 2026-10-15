"""Official MCP SDK boundary for approved, authenticated loopback read-only tools.

No OAuth discovery, shell transport, remote egress, SSE, redirects or retries.
Authorization/signing remains in Core; this adapter verifies a Core invocation.
"""
from __future__ import annotations

import asyncio
import json
import time
import threading
import hmac
from collections import deque
from datetime import timedelta

import httpx
from pydantic import SecretStr

from modules.core.errors import sanitize
from packages.contracts.bench import evidence_hash, strict_json_loads
from packages.contracts.tool import MCPApproval, MCPInvocation, MCPResultEvidence, PROTOCOL, checked_data


class MCPBoundaryError(LookupError):
    def __init__(self):
        super().__init__("Approved MCP read could not be verified.")


class BoundedMCPTransport(httpx.AsyncBaseTransport):
    """A policy wrapper around HTTP transport, not a JSON-RPC implementation."""
    def __init__(self, adapter, deadline, input_hash=None, reauthorize=None):
        self.adapter, self.deadline = adapter, deadline
        self.inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self.requests = 0
        self.tool_request_id = None
        self.input_hash = input_hash
        self.reauthorize = reauthorize

    async def handle_async_request(self, request):
        spec = self.adapter.approval.server
        self.requests += 1
        if (str(request.url) != spec.endpoint or request.method not in {"POST", "GET"}
                or self.requests > 8 or time.time() >= self.deadline
                or request.headers.get("authorization") != "Bearer " + self.adapter._secret.get_secret_value()):
            raise MCPBoundaryError()
        if request.method == "POST":
            body = strict_json_loads(request.content)
            method = body.get("method")
            if method not in {"initialize", "notifications/initialized", "tools/list", "tools/call", "notifications/cancelled"}:
                raise MCPBoundaryError()
            if method == "tools/call":
                if (self.tool_request_id is not None or body.get("params", {}).get("name") != spec.tool_name
                        or self.input_hash != evidence_hash(body.get("params", {}).get("arguments"))
                        or self.reauthorize is None):
                    raise MCPBoundaryError()
                self.reauthorize()
                self.tool_request_id = body.get("id")
        response = await self.inner.handle_async_request(request)
        try:
            if (response.status_code not in {200, 202, 405}
                    or response.headers.get("mcp-session-id")
                    or response.headers.get("content-encoding", "identity").lower() != "identity"):
                raise MCPBoundaryError()
            if response.status_code == 405 and request.method != "GET":
                raise MCPBoundaryError()
            length = response.headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) > spec.max_response_bytes):
                raise MCPBoundaryError()
            raw = bytearray()
            async for part in response.aiter_raw():
                raw.extend(part)
                if len(raw) > spec.max_response_bytes:
                    raise MCPBoundaryError()
            if raw:
                if response.headers.get("content-type", "").split(";")[0].lower() != "application/json":
                    raise MCPBoundaryError()
                parsed = strict_json_loads(raw)
                if sanitize(parsed, credentials=(self.adapter._secret.get_secret_value(),)) != parsed:
                    raise MCPBoundaryError()
            return httpx.Response(response.status_code, content=bytes(raw),
                headers={"content-type": "application/json"}, request=request)
        finally:
            await response.aclose()

    async def aclose(self):
        await self.inner.aclose()


class MCPAdapter:
    def __init__(self, approval: MCPApproval, secret: SecretStr):
        self.approval = MCPApproval.model_validate_json(approval.model_dump_json())
        self._secret = secret
        self._seen = set()
        self._attempts = deque()
        self._admission = threading.Lock()

    def connection_matches(self, identity, derive):
        return hmac.compare_digest(identity, derive(self._secret))

    async def _session(self, deadline, operation, input_hash=None, reauthorize=None):
        # Lazy imports keep SDK dependencies out of the confined Hermes process.
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        spec = self.approval.server
        transport = BoundedMCPTransport(self, deadline, input_hash, reauthorize)
        headers = {"Authorization": "Bearer " + self._secret.get_secret_value(),
            "Origin": spec.endpoint.removesuffix("/mcp"), "Accept-Encoding": "identity",
            "X-ARYN-Organization": spec.organization_id, "X-ARYN-Project": spec.project_id}
        seconds = min(spec.timeout_seconds, deadline - time.time())
        if seconds <= 0:
            raise TimeoutError("MCP deadline expired.")
        try:
            async with asyncio.timeout(seconds):
                async with httpx.AsyncClient(transport=transport, headers=headers, trust_env=False,
                        follow_redirects=False, timeout=seconds) as client:
                    async with streamable_http_client(spec.endpoint, http_client=client,
                            terminate_on_close=False) as (read, write, _):
                        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=seconds)) as session:
                            initialized = await session.initialize()
                            if (initialized.protocolVersion != PROTOCOL
                                    or initialized.serverInfo.name != spec.server_name
                                    or initialized.serverInfo.version != spec.server_version
                                    or initialized.capabilities.tools is None):
                                raise MCPBoundaryError()
                            catalog = await session.list_tools()
                            names = [tool.name for tool in catalog.tools]
                            if catalog.nextCursor or len(names) > 16 or len(set(names)) != len(names):
                                raise MCPBoundaryError()
                            tool = next((tool for tool in catalog.tools if tool.name == spec.tool_name), None)
                            if (tool is None or tool.inputSchema != spec.declaration.input_schema
                                    or tool.outputSchema != spec.output_schema
                                    or tool.annotations is None or tool.annotations.readOnlyHint is not True):
                                raise MCPBoundaryError()
                            return await operation(session, transport)
        except (TimeoutError, asyncio.CancelledError):
            raise
        except Exception:
            # SDK/provider error bodies never enter public errors or audit.
            raise MCPBoundaryError() from None

    async def discover(self):
        async def observed(session, transport):
            return {"protocol": PROTOCOL, "network_requests": transport.requests}
        return await self._session(time.time() + self.approval.server.timeout_seconds, observed)

    async def invoke(self, arguments, invocation: MCPInvocation, verifier, reauthorize):
        invocation = MCPInvocation.model_validate_json(invocation.model_dump_json())
        arguments = strict_json_loads(json.dumps(arguments, allow_nan=False))
        spec, approval = self.approval.server, self.approval
        checked_data(arguments, spec.declaration.input_schema, spec.max_response_bytes)
        if (invocation.organization_id != spec.organization_id or invocation.project_id != spec.project_id
                or invocation.binding_hash != approval.binding_hash
                or invocation.input_hash != evidence_hash(arguments)
                or invocation.deadline_at > approval.expires_at or time.time() >= invocation.deadline_at
                or not verifier("mcp_tool_call", invocation.payload(), invocation.attestation)):
            raise MCPBoundaryError()
        key = (invocation.run_id, invocation.call_id)
        stamp = time.monotonic()
        with self._admission:
            while self._attempts and stamp - self._attempts[0] >= 60:
                self._attempts.popleft()
            if key in self._seen or len(self._seen) >= 128 or len(self._attempts) >= spec.calls_per_minute:
                raise MCPBoundaryError()
            self._seen.add(key)
            self._attempts.append(stamp)
        started = time.perf_counter()

        async def call(session, transport):
            # Refresh Core permission, claim/owner, version/assignment and approval
            # after discovery, immediately before dispatching tools/call.
            reauthorize()
            result = await session.call_tool(spec.tool_name, arguments)
            if result.isError or result.structuredContent is None or len(result.content) != 1:
                raise MCPBoundaryError()
            content = result.content[0]
            if content.type != "text" or strict_json_loads(content.text) != result.structuredContent:
                raise MCPBoundaryError()
            data = checked_data(result.structuredContent, spec.output_schema, spec.max_response_bytes)
            evidence = {"run_id": invocation.run_id, "call_id": invocation.call_id,
                "organization_id": spec.organization_id, "project_id": spec.project_id,
                "server_id": spec.server_id, "server_name": spec.server_name, "server_version": spec.server_version,
                "remote_tool": spec.tool_name, "binding_hash": approval.binding_hash,
                "schema_hash": spec.schema_hash, "endpoint_hash": evidence_hash(spec.endpoint),
                "protocol": PROTOCOL, "source": "authenticated_loopback_mcp",
                "protocol_request_id": transport.tool_request_id, "network_requests": transport.requests,
                "input_hash": invocation.input_hash, "output_hash": evidence_hash(data),
                "result_bytes": len(json.dumps(data, sort_keys=True).encode()),
                "duration_seconds": time.perf_counter() - started}
            return data, MCPResultEvidence.model_validate(evidence).model_dump(mode="json")
        return await self._session(min(invocation.deadline_at, approval.expires_at), call, invocation.input_hash, reauthorize)
