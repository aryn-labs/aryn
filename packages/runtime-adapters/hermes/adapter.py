"""Hermes Runtime Adapter for ARYN infrastructure.

Provides an isolated, secure, typed interface to the local Hermes Gateway HTTP API.
Strictly adheres to ARYN-TECH-001 ADR-004 and ARYN-SEC-001.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import httpx

from packages.contracts.core import SecurityContext
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeTrace,
)
from .exceptions import (
    HermesAdapterError,
    RunNotFoundError,
    RuntimeAuthenticationError,
    RuntimeConnectionError,
    RuntimeSecurityError,
    RuntimeTimeoutError,
)

logger = logging.getLogger("aryn.runtime.hermes")


class HermesRuntimeAdapter(RuntimeAdapter):
    """Hermes Agent v0.21.5 HTTP API Adapter."""

    RISKY_TOOLSETS = frozenset({"terminal", "file", "code_execution", "browser"})

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8642",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        enforce_loopback: bool = True,
        enforce_tool_confinement: bool = True,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self.enforce_loopback = enforce_loopback
        self.enforce_tool_confinement = enforce_tool_confinement
        self._custom_client = http_client

        if self.enforce_loopback:
            self._verify_loopback_only(self.base_url)

    @staticmethod
    def _verify_loopback_only(url: str) -> None:
        """Enforces that the adapter connects ONLY to loopback addresses."""
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeSecurityError(
                f"Security policy violation: Hermes adapter must bind only to loopback. "
                f"Rejected target host: '{hostname}'."
            )

    def _headers(self, require_auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if require_auth:
            if not self.api_key:
                raise RuntimeAuthenticationError("API_SERVER_KEY is mandatory for authenticated Hermes endpoints.")
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.AsyncClient(timeout=self.timeout)

    async def health(self) -> RuntimeHealth:
        """Inspects Hermes /health and /health/detailed."""
        client = self._get_client()
        should_close = self._custom_client is None
        try:
            # 1. Basic unauthenticated health check
            try:
                resp = await client.get(f"{self.base_url}/health", timeout=self.timeout)
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError(f"Failed to connect to Hermes at {self.base_url}: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError(f"Health check timed out: {exc}") from exc

            if resp.status_code != 200:
                return RuntimeHealth(
                    is_healthy=False,
                    status=f"http_{resp.status_code}",
                    platform="hermes-agent",
                    version="unknown",
                    listener_url=self.base_url,
                    details={"error": resp.text},
                )

            data = resp.json()
            is_healthy = data.get("status") == "ok"
            version = data.get("version", "0.21.5")
            platform = data.get("platform", "hermes-agent")

            # 2. Detailed health check (requires auth if api_key present)
            details = {}
            if self.api_key:
                try:
                    det_resp = await client.get(
                        f"{self.base_url}/health/detailed",
                        headers=self._headers(require_auth=True),
                        timeout=self.timeout,
                    )
                    if det_resp.status_code == 200:
                        details = det_resp.json()
                except Exception as e:
                    logger.warning("Could not fetch detailed health: %s", e)

            return RuntimeHealth(
                is_healthy=is_healthy,
                status=data.get("status", "ok"),
                platform=platform,
                version=version,
                listener_url=self.base_url,
                details=details,
            )
        finally:
            if should_close:
                await client.aclose()

    async def capabilities(self) -> RuntimeCapabilities:
        """Queries /v1/toolsets to discover tool states and verify confinement."""
        client = self._get_client()
        should_close = self._custom_client is None
        try:
            try:
                resp = await client.get(
                    f"{self.base_url}/v1/toolsets",
                    headers=self._headers(require_auth=True),
                    timeout=self.timeout,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError(f"Connection to Hermes failed: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError(f"Capabilities check timed out: {exc}") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Hermes API server rejected credentials for /v1/toolsets.")
            if resp.status_code != 200:
                raise HermesAdapterError(f"Failed to query /v1/toolsets: HTTP {resp.status_code} - {resp.text}")

            body = resp.json()
            toolsets = body.get("data", [])
            available = [ts.get("name") for ts in toolsets if ts.get("name")]
            enabled = [ts.get("name") for ts in toolsets if ts.get("enabled", False)]

            # Check if any dangerous tools are active
            active_risky = set(enabled).intersection(self.RISKY_TOOLSETS)
            tools_confined = len(active_risky) == 0

            if self.enforce_tool_confinement and not tools_confined:
                raise RuntimeSecurityError(
                    f"Security policy violation: Risky tools active on Hermes API: {sorted(active_risky)}. "
                    "Expected platform_toolsets.api_server to deny host access tools."
                )

            return RuntimeCapabilities(
                enabled_toolsets=enabled,
                available_toolsets=available,
                tools_confined=tools_confined,
                supports_cancellation=True,
                supports_streaming=True,
                details={"active_risky_tools": list(active_risky), "total_toolsets": len(toolsets)},
            )
        finally:
            if should_close:
                await client.aclose()

    async def start_run(self, request: RunRequest, context: SecurityContext) -> str:
        """Starts an agent run via POST /v1/runs with mandatory security assertions."""
        # Pre-execution security check
        if self.enforce_tool_confinement:
            caps = await self.capabilities()
            if not caps.tools_confined:
                raise RuntimeSecurityError("Cannot dispatch run: runtime tools confinement failed.")

        client = self._get_client()
        should_close = self._custom_client is None
        try:
            payload: Dict[str, Any] = {
                "input": request.prompt,
                "model": request.model,
            }
            if request.system_instructions:
                payload["instructions"] = request.system_instructions

            # Inject session scoping if specified
            headers = self._headers(require_auth=True)
            if request.session_id:
                headers["X-Hermes-Session-Key"] = request.session_id

            try:
                resp = await client.post(
                    f"{self.base_url}/v1/runs",
                    headers=headers,
                    json=payload,
                    timeout=request.timeout_seconds,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError(f"Connection failed when starting run: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError(f"Start run request timed out: {exc}") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when creating run.")
            if resp.status_code not in (200, 201, 202):
                raise HermesAdapterError(f"Start run failed: HTTP {resp.status_code} - {resp.text}")

            data = resp.json()
            run_id = data.get("run_id") or data.get("id")
            if not run_id:
                raise HermesAdapterError(f"Invalid response from /v1/runs: missing run_id in {data}")

            return str(run_id)
        finally:
            if should_close:
                await client.aclose()

    async def get_result(self, run_id: str, context: SecurityContext) -> RunResult:
        """Retrieves the result of a run via GET /v1/runs/{run_id}."""
        client = self._get_client()
        should_close = self._custom_client is None
        try:
            try:
                resp = await client.get(
                    f"{self.base_url}/v1/runs/{run_id}",
                    headers=self._headers(require_auth=True),
                    timeout=self.timeout,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError(f"Connection failed when polling result: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError(f"Polling result timed out: {exc}") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when retrieving run result.")
            if resp.status_code == 404:
                raise RunNotFoundError(f"Run '{run_id}' not found.")
            if resp.status_code != 200:
                raise HermesAdapterError(f"Failed to fetch run: HTTP {resp.status_code} - {resp.text}")

            data = resp.json()
            raw_status = data.get("status", "").lower()
            status_map = {
                "queued": RunStatus.QUEUED,
                "started": RunStatus.STARTED,
                "running": RunStatus.RUNNING,
                "completed": RunStatus.COMPLETED,
                "stopping": RunStatus.STOPPING,
                "cancelled": RunStatus.CANCELLED,
                "interrupted": RunStatus.CANCELLED,
                "failed": RunStatus.FAILED,
            }
            status = status_map.get(raw_status, RunStatus.RUNNING)

            usage_dict = data.get("usage") or {}
            usage = RunUsage(
                input_tokens=usage_dict.get("input_tokens", 0),
                output_tokens=usage_dict.get("output_tokens", 0),
                total_tokens=usage_dict.get("total_tokens", 0),
            )

            return RunResult(
                run_id=run_id,
                status=status,
                output=data.get("output", ""),
                usage=usage,
                model=data.get("model", ""),
                created_at=data.get("created_at", time.time()),
                completed_at=data.get("updated_at") if status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED) else None,
                error_message=data.get("error"),
                raw_response=data,
            )
        finally:
            if should_close:
                await client.aclose()

    async def cancel_run(self, run_id: str, context: SecurityContext) -> bool:
        """Interrupts a running agent via POST /v1/runs/{run_id}/stop."""
        client = self._get_client()
        should_close = self._custom_client is None
        try:
            try:
                resp = await client.post(
                    f"{self.base_url}/v1/runs/{run_id}/stop",
                    headers=self._headers(require_auth=True),
                    timeout=self.timeout,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError(f"Connection failed when cancelling run: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError(f"Cancel request timed out: {exc}") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when cancelling run.")
            if resp.status_code == 404:
                raise RunNotFoundError(f"Run '{run_id}' not found for cancellation.")
            if resp.status_code in (200, 202, 409):
                # 409 in Hermes means run is already terminal or not active
                return True

            return False
        finally:
            if should_close:
                await client.aclose()

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        """Retrieves execution trace and event snapshots."""
        # Query run state to obtain canonical trace metadata
        result = await self.get_result(run_id, context)
        events = []
        if "last_event" in result.raw_response:
            events.append({
                "name": result.raw_response.get("last_event"),
                "status": result.status.value,
                "timestamp": result.completed_at or result.created_at,
            })
        return RuntimeTrace(
            run_id=run_id,
            events=events,
            raw_trace=result.raw_response,
        )

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        """Direct synchronous turn execution via /v1/chat/completions."""
        # Pre-execution security check
        if self.enforce_tool_confinement:
            caps = await self.capabilities()
            if not caps.tools_confined:
                raise RuntimeSecurityError("Cannot execute direct turn: tool confinement failed.")

        client = self._get_client()
        should_close = self._custom_client is None
        start_time = time.time()
        try:
            messages: List[Dict[str, str]] = []
            if request.system_instructions:
                messages.append({"role": "system", "content": request.system_instructions})
            messages.append({"role": "user", "content": request.prompt})

            payload = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }

            try:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._headers(require_auth=True),
                    json=payload,
                    timeout=request.timeout_seconds,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError(f"Direct turn connection failed: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError(f"Direct turn timed out: {exc}") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when calling /v1/chat/completions.")
            if resp.status_code != 200:
                raise HermesAdapterError(f"Direct turn failed: HTTP {resp.status_code} - {resp.text}")

            data = resp.json()
            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            usage_dict = data.get("usage") or {}
            usage = RunUsage(
                input_tokens=usage_dict.get("prompt_tokens", 0),
                output_tokens=usage_dict.get("completion_tokens", 0),
                total_tokens=usage_dict.get("total_tokens", 0),
            )

            return RunResult(
                run_id=data.get("id", f"turn_{int(start_time)}"),
                status=RunStatus.COMPLETED,
                output=content,
                usage=usage,
                model=data.get("model", request.model),
                created_at=start_time,
                completed_at=time.time(),
                raw_response=data,
            )
        finally:
            if should_close:
                await client.aclose()
