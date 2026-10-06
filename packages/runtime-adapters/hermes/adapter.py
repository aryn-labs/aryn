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
    ModelUnavailableError,
    GatewayUnavailableError,
    ModelIdentityError,
    RuntimeGatewayError,
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeModelAvailability,
    RuntimeTrace,
)
from packages.model_adapters.gateway import NineRouterGateway
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
        model_gateway: Optional[NineRouterGateway] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self.enforce_loopback = enforce_loopback
        self.enforce_tool_confinement = enforce_tool_confinement
        self._custom_client = http_client
        self.model_gateway = model_gateway or NineRouterGateway()
        self._gateway_binding = {}

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
        return httpx.AsyncClient(timeout=self.timeout, trust_env=False, follow_redirects=False)

    def _run_headers(self, request, context):
        import hashlib
        import uuid
        headers = self._headers()
        key = request.idempotency_key or uuid.uuid4().hex
        scope = "\0".join((context.organization_id, context.project_id, key))
        headers["Idempotency-Key"] = "aryn_" + hashlib.sha256(scope.encode()).hexdigest()
        if request.session_id:
            headers["X-Hermes-Session-Key"] = request.session_id
        return headers

    async def discover_models(self, *, refresh=False):
        return await self.model_gateway.discover(refresh=refresh)

    async def model_availability(self, model, *, refresh=False):
        return await self.model_gateway.availability(model, refresh=refresh)

    async def gateway_binding(self):
        """Require a runtime-side routing/actual-model contract; echoed model is not proof."""
        client = self._get_client()
        try:
            response = await client.get(f"{self.base_url}/aryn/gateway", headers=self._headers(), timeout=self.timeout)
            if response.status_code != 200:
                return False
            data = response.json()
            self._gateway_binding = data if isinstance(data, dict) else {}
            return (isinstance(data, dict) and data.get("gateway") == "9Router"
                    and data.get("base_url") == self.model_gateway.settings.base_url
                    and data.get("exact_model_enforced") is True
                    and data.get("runtime_backend") == "Hermes")
        except (httpx.HTTPError, ValueError, HermesAdapterError):
            return False
        finally:
            if self._custom_client is None:
                await client.aclose()

    async def require_model_available(self, model):
        discovery = await self.discover_models(refresh=True)
        if not discovery.discovery_valid:
            raise GatewayUnavailableError()
        await super().require_model_available(model)
        if not await self.gateway_binding():
            raise RuntimeGatewayError()

    def _provenance(self, data, requested):
        evidence = data.get("aryn")
        if (not isinstance(evidence, dict) or evidence.get("gateway") != "9Router"
                or evidence.get("runtime_backend") != "Hermes"
                or evidence.get("requested_model") != requested
                or evidence.get("actual_model_source") != "gateway_response"
                or not isinstance(evidence.get("actual_model"), str) or not evidence["actual_model"]):
            raise RuntimeGatewayError()
        if evidence["actual_model"] != requested:
            raise ModelIdentityError()
        provider = evidence.get("provider")
        # Only a bounded identifier; upstream payloads and error text never become metadata.
        from packages.model_adapters.gateway import MODEL_ID
        if not isinstance(provider, str) or not MODEL_ID.fullmatch(provider):
            provider = None
        return dict(requested_model=requested, actual_model=evidence["actual_model"],
                    gateway="9Router", runtime_backend="Hermes", provider=provider)

    def _assert_no_secret(self, value):
        keys = (self.api_key, self.model_gateway.settings.api_key.get_secret_value())
        import json
        text = json.dumps(value, ensure_ascii=False)
        if any(key and key in text for key in keys):
            raise RuntimeSecurityError("Runtime response contains a protected credential; result rejected.")

    def _check_model_rejection(self, response, model):
        """Recognize an explicit provider rejection without exposing its error body."""
        if response.status_code == 200:
            return
        try:
            body = response.json()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = error.get("message", "") if isinstance(error, dict) else error
            code = error.get("code", "") if isinstance(error, dict) else ""
            if code == "actual_model_mismatch":
                raise ModelIdentityError()
            if code in {"missing_gateway_provenance", "gateway_route_mismatch"}:
                raise RuntimeGatewayError()
            message = message.lower() if isinstance(message, str) else ""
            rejected = (isinstance(code, str) and code in {"model_not_found", "unknown_model", "model_not_available"}) or (
                "model" in message and any(phrase in message for phrase in ("not found", "does not exist", "not available", "unknown model", "invalid model")))
        except ValueError:
            rejected = False
        if rejected:
            self.model_gateway.reject(model)
            raise ModelUnavailableError(RuntimeModelAvailability(
                model=model, status="unavailable", source="provider_rejection", reason="provider_rejected"))

    async def health(self) -> RuntimeHealth:
        """Inspects Hermes /health and /health/detailed."""
        client = self._get_client()
        should_close = self._custom_client is None
        try:
            # 1. Basic unauthenticated health check
            try:
                resp = await client.get(f"{self.base_url}/health", timeout=self.timeout)
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError("Runtime connection or timeout failure.") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError("Runtime connection or timeout failure.") from exc

            if resp.status_code != 200:
                return RuntimeHealth(
                    is_healthy=False,
                    status=f"http_{resp.status_code}",
                    platform="hermes-agent",
                    version="unknown",
                    listener_url=self.base_url,
                    details={"error": "runtime_http_failure"},
                )

            data = resp.json()
            self._assert_no_secret(data)
            is_healthy = data.get("status") == "ok"
            version = data.get("version", "unknown")
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
                        self._assert_no_secret(details)
                except Exception as e:
                    details = {}
                    logger.warning("Could not fetch detailed runtime health (%s)", type(e).__name__)

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
                raise RuntimeConnectionError("Runtime connection or timeout failure.") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError("Runtime connection or timeout failure.") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Hermes API server rejected credentials for /v1/toolsets.")
            if resp.status_code != 200:
                raise HermesAdapterError(f"Failed to query /v1/toolsets: HTTP {resp.status_code}")

            body = resp.json()
            self._assert_no_secret(body)
            toolsets = body.get("data") if isinstance(body, dict) else None
            if not isinstance(toolsets, list) or any(
                not isinstance(ts, dict) or not isinstance(ts.get("name"), str)
                or not ts["name"] or not isinstance(ts.get("enabled"), bool)
                for ts in toolsets
            ):
                raise HermesAdapterError("Tool confinement cannot be verified from malformed capabilities.")
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
            if not caps.tools_confined or caps.enabled_toolsets:
                raise RuntimeSecurityError("Cannot dispatch run: runtime tools confinement failed.")

        await self.require_model_available(request.model)
        if self._gateway_binding.get("async_provenance") is not True:
            raise RuntimeGatewayError()

        client = self._get_client()
        should_close = self._custom_client is None
        try:
            payload: Dict[str, Any] = {
                "input": request.prompt,
                "model": request.model,
                "provider": "9router",
                "model_options": {"temperature": request.temperature, "max_tokens": request.max_tokens},
            }
            if request.system_instructions:
                payload["instructions"] = request.system_instructions

            # Inject session scoping if specified
            headers = self._run_headers(request, context)

            try:
                resp = await client.post(
                    f"{self.base_url}/v1/runs",
                    headers=headers,
                    json=payload,
                    timeout=request.timeout_seconds,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError("Runtime connection or timeout failure.") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError("Runtime connection or timeout failure.") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when creating run.")
            self._check_model_rejection(resp, request.model)
            if resp.status_code not in (200, 201, 202):
                raise HermesAdapterError(f"Start run failed: HTTP {resp.status_code}")

            data = resp.json()
            self._assert_no_secret(data)
            run_id = data.get("run_id") or data.get("id")
            if not run_id:
                raise HermesAdapterError("Invalid response from /v1/runs: missing run_id")

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
                raise RuntimeConnectionError("Runtime connection or timeout failure.") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError("Runtime connection or timeout failure.") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when retrieving run result.")
            if resp.status_code == 404:
                raise RunNotFoundError(f"Run '{run_id}' not found.")
            if resp.status_code != 200:
                raise HermesAdapterError(f"Failed to fetch run: HTTP {resp.status_code}")

            data = resp.json()
            if data.get("run_id", data.get("id")) != run_id:
                raise HermesAdapterError("Runtime returned a different run identifier.")
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

            provenance = self._provenance(data, data.get("model", "")) if status == RunStatus.COMPLETED else {}
            self._assert_no_secret(data)
            return RunResult(
                **provenance,
                run_id=run_id,
                status=status,
                output=data.get("output", ""),
                usage=usage,
                model=data.get("model", ""),
                created_at=data.get("created_at", time.time()),
                completed_at=data.get("updated_at") if status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED) else None,
                error_message="Runtime failed." if data.get("error") else None,
                raw_response={},
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
                raise RuntimeConnectionError("Runtime connection or timeout failure.") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError("Runtime connection or timeout failure.") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when cancelling run.")
            if resp.status_code == 404:
                raise RunNotFoundError(f"Run '{run_id}' not found for cancellation.")
            if resp.status_code in (200, 202):
                # This acknowledges a stop request; Core verifies the resulting state.
                return True

            return False
        finally:
            if should_close:
                await client.aclose()

    async def get_trace(self, run_id: str, context: SecurityContext) -> RuntimeTrace:
        """The current gateway exposes no supported structured trace contract."""
        return RuntimeTrace(
            run_id=run_id,
            available=False,
            unavailability_reason="Trace Hermes terstruktur belum tersedia. Audit Core tetap tersedia.",
        )

    async def execute_direct_turn(self, request: RunRequest, context: SecurityContext) -> RunResult:
        """Direct synchronous turn execution via /v1/chat/completions."""
        # Pre-execution security check
        if self.enforce_tool_confinement:
            caps = await self.capabilities()
            if not caps.tools_confined or caps.enabled_toolsets:
                raise RuntimeSecurityError("Cannot execute direct turn: tool confinement failed.")

        await self.require_model_available(request.model)

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
                "provider": "9router",
                "model_options": {"temperature": request.temperature, "max_tokens": request.max_tokens},
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }

            try:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._run_headers(request, context),
                    json=payload,
                    timeout=request.timeout_seconds,
                )
            except httpx.ConnectError as exc:
                raise RuntimeConnectionError("Runtime connection or timeout failure.") from exc
            except httpx.TimeoutException as exc:
                raise RuntimeTimeoutError("Runtime connection or timeout failure.") from exc

            if resp.status_code == 401:
                raise RuntimeAuthenticationError("Unauthorized when calling /v1/chat/completions.")
            self._check_model_rejection(resp, request.model)
            if resp.status_code != 200:
                raise HermesAdapterError(f"Direct turn failed: HTTP {resp.status_code}")

            data = resp.json()
            if not isinstance(data, dict) or any(
                not isinstance(data.get(field), str) or not data[field] for field in ("id", "model")
            ):
                raise HermesAdapterError("Direct response is missing actual run/model provenance.")
            choices = data.get("choices", [])
            if (not isinstance(choices, list) or not choices or not isinstance(choices[0], dict)
                    or not isinstance(choices[0].get("message"), dict)
                    or not isinstance(choices[0]["message"].get("content"), str)):
                raise HermesAdapterError("Direct response is missing actual completion content.")
            provenance = self._provenance(data, request.model)
            self._assert_no_secret(data)
            if data["model"] != request.model:
                raise ModelIdentityError()
            if (choices[0].get("finish_reason") != "stop" or data.get("hermes", {}).get("failed")
                    or data.get("hermes", {}).get("partial")):
                raise HermesAdapterError("Runtime completion is incomplete or failed.")
            content = choices[0]["message"]["content"]
            usage_dict = data.get("usage") or {}
            if not isinstance(usage_dict, dict) or any(type(usage_dict.get(field)) is not int or usage_dict[field] < 0
                   for field in ("prompt_tokens", "completion_tokens", "total_tokens")):
                raise HermesAdapterError("Direct response is missing actual token usage.")
            usage = RunUsage(
                input_tokens=usage_dict.get("prompt_tokens", 0),
                output_tokens=usage_dict.get("completion_tokens", 0),
                total_tokens=usage_dict.get("total_tokens", 0),
            )

            return RunResult(
                run_id=data["id"],
                status=RunStatus.COMPLETED,
                output=content,
                usage=usage,
                model=provenance["actual_model"],
                **provenance,
                created_at=start_time,
                completed_at=time.time(),
                raw_response={},
            )
        finally:
            if should_close:
                await client.aclose()
