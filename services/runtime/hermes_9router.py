"""Runtime-side binding for the installed Hermes API and 9Router.

Run with the installed Hermes Python environment, --hermes-source pointing to its
checkout. No installed sources, config, toolsets, provider credentials or secrets
files are changed. The API/native AIAgent remain Hermes; only model transport is bound.
"""

import argparse
import asyncio
from contextvars import ContextVar
import json
import math
from pathlib import Path
import sys

from packages.model_adapters.gateway import MODEL_ID
from services.runtime.gateway_transport import ExactGatewayTransport, ModelReceipt

TURN = ContextVar("aryn_gateway_turn", default=None)


def build_adapter(settings, runtime_key, port=None):
    if not isinstance(runtime_key, str) or len(runtime_key) < 32:
        raise ValueError("Explicit runtime authentication is required.")
    from modules.core.errors import protect_diagnostic_logging
    protect_diagnostic_logging((runtime_key, settings.api_key.get_secret_value()))
    if port is None:
        from packages.config import get_settings
        port = get_settings().runtime_port
    # Hermes imports its dotenv loader during run_agent import. Disable that loader
    # in this dedicated process: gateway credentials are supplied explicitly only.
    from hermes_cli import env_loader
    env_loader.load_hermes_dotenv = lambda **kwargs: []
    from aiohttp import web
    import httpx
    from openai import OpenAI
    from run_agent import AIAgent
    from agent import title_generator
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter, _require_auth, _hermes_version
    from gateway.run import _load_gateway_config
    from hermes_cli.tools_config import _get_platform_tools

    def require_confinement():
        # Read security configuration through Hermes, without modifying it.
        if _get_platform_tools(_load_gateway_config(), "api_server"):
            raise RuntimeError("Hermes toolsets must already be disabled.")

    require_confinement()
    # Session naming must not dispatch an additional, ungoverned model request.
    # This affects only the dedicated ARYN process, never installed Hermes config.
    title_generator._auto_title_enabled = lambda: False

    class GovernedAgent(AIAgent):
        def __init__(self, receipt, **kwargs):
            self.aryn_receipt = receipt
            super().__init__(**kwargs)
            self._disable_streaming = True
            # No auxiliary model route (compression/review/memory) bypasses this transport.
            self.compression_enabled = False

        def _create_openai_client(self, client_kwargs, **kwargs):
            # Rebuilds after interruption are guarded by this same constructor.
            if client_kwargs.get("base_url", "").rstrip("/") != settings.base_url:
                raise RuntimeError("Alternate model gateway is forbidden.")
            client = httpx.Client(transport=ExactGatewayTransport(settings, self.aryn_receipt),
                                  trust_env=False, follow_redirects=False, timeout=30)
            return OpenAI(base_url=settings.base_url, api_key="gateway-transport-managed",
                          http_client=client, max_retries=0)

        def run_conversation(self, *args, **kwargs):
            result = super().run_conversation(*args, **kwargs)
            if not self.aryn_receipt.evidence():
                return {"completed": False, "failed": True, "final_response": "",
                        "error": self.aryn_receipt.failure or "Missing gateway model evidence."}
            return result

    class BoundHermesAPI(APIServerAdapter):
        async def connect(self, *, is_reconnect=False):
            # Do not inherit native connect: it adds profile ingress, plugin handlers
            # and background native work independently of _http_route_table().
            require_confinement()
            self._app = self.confined_application()
            self._runner = web.AppRunner(self._app, access_log=None)
            await self._runner.setup()
            try:
                self._site = web.TCPSite(self._runner, "127.0.0.1", self._port)
                await self._site.start()
                self._mark_connected(listener_base=f"http://127.0.0.1:{self._port}")
            except Exception:
                await self._runner.cleanup()
                self._runner = None
                raise
            return True

        def confined_application(self):
            """The exact application used by connect, with no native/plugin ingress."""
            from modules.core.errors import sanitize

            @web.middleware
            async def boundary(request, handler):
                if request.method == "GET" and request.path == "/health":
                    return await handler(request)
                if request.match_info.http_exception is not None:
                    return web.json_response({"error": {"code": "operation_not_available"}}, status=404)
                if request.headers.get("Origin") or request.headers.get("Upgrade"):
                    return web.json_response({"error": {"code": "browser_transport_forbidden"}}, status=403)
                if self._check_auth(request) is not None:
                    return web.json_response({"error": {"code": "runtime_authentication_required"}}, status=401)
                if any(request.headers.get(name) is not None for name in ("X-Hermes-Session-Id", "X-Hermes-Session-Key")):
                    return web.json_response({"error": {"code": "native_session_selection_forbidden"}}, status=403)
                try:
                    require_confinement()
                    response = await handler(request)
                    if isinstance(response, web.Response) and response.content_type == "application/json":
                        data = json.loads(response.body)
                        data = sanitize(data, credentials=(runtime_key, settings.api_key.get_secret_value()))
                        if response.status >= 400 and isinstance(data, dict) and "error" in data:
                            error = data["error"]
                            code = error.get("code", "runtime_request_rejected") if isinstance(error, dict) else "runtime_request_rejected"
                            # Raw provider/native message text is never a transport contract.
                            data = {"error": {"code": code if isinstance(code, str) and code.replace("_", "").isalnum() else "runtime_request_rejected"}}
                        return web.json_response(data, status=response.status)
                    return response
                except Exception:
                    return web.json_response({"error": {"code": "runtime_operation_failed"}}, status=502)

            application = web.Application(middlewares=[boundary], client_max_size=65536)
            for method, path, handler in self._http_route_table():
                application.router.add_route(method, path, handler)
            return application

        def validate_text_request(self, body, *, asynchronous=False):
            common = {"model", "provider", "model_options", "temperature", "max_tokens"}
            allowed = common | ({"input", "instructions"} if asynchronous else {"messages", "stream"})
            if not isinstance(body, dict) or set(body) - allowed:
                raise ValueError("Only governed text fields are allowed.")
            if body.get("provider") != "9router" or not isinstance(body.get("model"), str) or not MODEL_ID.fullmatch(body["model"]):
                raise ValueError("Exact model/provider required.")
            if body.get("stream", False) is not False:
                raise ValueError("Native streaming is unavailable.")
            options = body.get("model_options", {})
            if not isinstance(options, dict) or set(options) - {"temperature", "max_tokens"}:
                raise ValueError("Request cannot configure runtime capabilities.")
            for values in (body, options):
                temperature = values.get("temperature", 0.3)
                maximum = values.get("max_tokens", 2048)
                if (type(temperature) not in {int, float} or not math.isfinite(temperature) or not 0 <= temperature <= 2
                        or type(maximum) is not int or not 1 <= maximum <= 4096):
                    raise ValueError("Invalid execution limits.")
            # Native sync/async handlers read different locations. A duplicate
            # or alternate location must agree, never silently weaken a cap.
            primary, alternate = (options, body) if asynchronous else (body, options)
            for name, default in (("temperature", 0.7 if asynchronous else 0.3), ("max_tokens", 2048)):
                if name in alternate and alternate[name] != primary.get(name, default):
                    raise ValueError("Ambiguous execution limits.")
            if asynchronous:
                if not isinstance(body.get("input"), str) or not body["input"]:
                    raise ValueError("Text input required.")
                if "instructions" in body and not isinstance(body["instructions"], str):
                    raise ValueError("Text instructions required.")
            else:
                messages = body.get("messages")
                if not isinstance(messages, list) or not 1 <= len(messages) <= 2:
                    raise ValueError("Single text turn required.")
                if messages[-1].get("role") != "user" or (len(messages) == 2 and messages[0].get("role") != "system"):
                    raise ValueError("Single text turn required.")
                if any(not isinstance(m, dict) or set(m) != {"role", "content"} or not isinstance(m["content"], str) for m in messages):
                    raise ValueError("No tool or multimodal input allowed.")

        def _set_run_status(self, run_id, status, **fields):
            receipt = TURN.get()
            if status == "completed":
                proof = receipt.evidence() if receipt else None
                if not proof:
                    status, fields = "failed", {"error": "Missing gateway model evidence."}
                else:
                    fields["aryn"] = proof
            return super()._set_run_status(run_id, status, **fields)

        async def _handle_runs(self, request):
            body = await request.json()
            try:
                self.validate_text_request(body, asynchronous=True)
            except (ValueError, TypeError, AttributeError):
                return web.json_response({"error": {"code": "confined_text_required"}}, status=422)
            if any(key and key in json.dumps(body, ensure_ascii=False) for key in (runtime_key, settings.api_key.get_secret_value())):
                return web.json_response({"error": {"code": "protected_credential_input"}}, status=422)
            options = body.get("model_options") or {}
            receipt = ModelReceipt(body.get("model", ""), transport={"temperature": options.get("temperature", 0.7),
                                                                     "max_tokens": options.get("max_tokens", 2048)})
            token = TURN.set(receipt)
            try:
                return await super()._handle_runs(request)
            finally:
                TURN.reset(token)

        async def _run_agent(self, **kwargs):
            # Hermes' executor does not propagate ContextVars. Carry the receipt
            # explicitly through its per-turn options; never accept it from HTTP input.
            options = dict(kwargs.get("model_options") or {})
            options["_aryn_receipt"] = TURN.get()
            kwargs["model_options"] = options
            return await super()._run_agent(**kwargs)

        def _http_route_table(self):
            return [
                ("GET", "/health", self.aryn_health),
                ("GET", "/health/detailed", self.aryn_health),
                ("GET", "/v1/toolsets", self.aryn_toolsets),
                ("GET", "/v1/capabilities", self.aryn_capabilities),
                ("GET", "/aryn/gateway", self.aryn_gateway),
                ("POST", "/v1/chat/completions", self._handle_chat_completions),
                ("POST", "/v1/runs", self._handle_runs),
                ("GET", "/v1/runs/{run_id}", self._handle_get_run),
                ("POST", "/v1/runs/{run_id}/stop", self._handle_stop_run),
            ]

        async def aryn_health(self, request):
            return web.json_response({"status": "ok", "platform": "hermes-agent", "version": _hermes_version()})

        async def aryn_toolsets(self, request):
            require_confinement()
            return web.json_response({"data": []})

        async def aryn_capabilities(self, request):
            require_confinement()
            return web.json_response({"text_execution": True, "native_streaming": False,
                "tools": [], "jobs": False, "scheduler": False, "session_administration": False,
                "operations": [method + " " + path for method, path, _ in self._http_route_table()]})

        @_require_auth
        async def aryn_gateway(self, request):
            require_confinement()
            return web.json_response({"gateway": "9Router", "runtime_backend": "Hermes",
                                      "base_url": settings.base_url, "exact_model_enforced": True,
                                      "async_provenance": True})

        def _create_agent(self, **kwargs):
            require_confinement()
            model = kwargs.get("requested_model")
            if kwargs.get("requested_provider") != "9router" or not isinstance(model, str) or not MODEL_ID.fullmatch(model):
                raise RuntimeError("Explicit 9Router model selection required.")
            internal = (kwargs.get("model_options") or {}).get("_aryn_receipt")
            receipt = internal if isinstance(internal, ModelReceipt) else TURN.get()
            if receipt is None or receipt.requested_model != model:
                raise RuntimeError("Governed direct-turn context required.")
            options = receipt.transport or {}
            callbacks = {k: v for k, v in kwargs.items() if k.endswith("_callback")}
            agent = GovernedAgent(receipt, model=model, provider="custom", api_mode="chat_completions",
                                  base_url=settings.base_url, api_key="gateway-transport-managed",
                                  enabled_toolsets=[], fallback_model=None, max_iterations=1,
                                  max_tokens=options.get("max_tokens", 2048),
                                  request_overrides={"temperature": options.get("temperature", 0.3)},
                                  ephemeral_system_prompt=kwargs.get("ephemeral_system_prompt"),
                                  session_id=kwargs.get("session_id"), session_db=self._ensure_session_db(),
                                  platform="api_server", quiet_mode=True, verbose_logging=False,
                                  skip_context_files=True, skip_memory=True, skip_background_review=True,
                                  **callbacks)
            agent._hermes_api_runtime = {"provider": "custom", "model": model, "route_source": "aryn_9router"}
            return agent

        async def _handle_chat_completions(self, request):
            body = await request.json()
            try:
                self.validate_text_request(body)
            except (ValueError, TypeError, AttributeError):
                return web.json_response({"error": {"code": "confined_text_required"}}, status=422)
            if any(key and key in json.dumps(body, ensure_ascii=False) for key in (runtime_key, settings.api_key.get_secret_value())):
                return web.json_response({"error": {"code": "protected_credential_input"}}, status=422)
            if body.get("stream") is True:
                return web.json_response({"error": {"code": "stream_provenance_unavailable"}}, status=409)
            receipt = ModelReceipt(body.get("model", ""), transport={"temperature": body.get("temperature", 0.3),
                                                                    "max_tokens": body.get("max_tokens", 2048)})
            token = TURN.set(receipt)
            try:
                response = await super()._handle_chat_completions(request)
                if receipt.failure:
                    return web.json_response({"error": {"code": receipt.failure}}, status=409)
                if response.status != 200:
                    return response
                proof = receipt.evidence()
                if not proof:
                    return web.json_response({"error": {"code": receipt.failure or "missing_gateway_provenance"}}, status=409)
                data = json.loads(response.body)
                data["aryn"] = proof
                return web.json_response(data, headers={k: v for k, v in response.headers.items()
                                          if k.lower() in {"x-hermes-session-id", "x-hermes-session-key"}})
            finally:
                TURN.reset(token)

    return BoundHermesAPI(PlatformConfig(enabled=True, extra={"host": "127.0.0.1", "port": port,
                          "key": runtime_key, "direct_model_requests": False, "cors_origins": []}))


async def serve(args):
    from packages.config import get_settings
    aryn_settings = get_settings()
    settings = aryn_settings.gateway_settings
    runtime_key = aryn_settings.api_server_key.get_secret_value()
    if len(runtime_key) < 32:
        raise RuntimeError("Supply API_SERVER_KEY to the runtime and ARYN API process; no secret files are scanned.")
    sys.path.insert(0, str(Path(args.hermes_source).resolve()))
    port = args.port if args.port is not None else aryn_settings.runtime_port
    adapter = build_adapter(settings, runtime_key, port)
    if args.check:
        print("Hermes integration compatible; confinement verified; no inference dispatched.")
        return
    if not await adapter.connect():
        raise RuntimeError("Hermes API failed to bind.")
    try:
        await asyncio.Event().wait()
    finally:
        await adapter.disconnect()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-source", required=True)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--check", action="store_true")
    asyncio.run(serve(parser.parse_args()))


if __name__ == "__main__":
    main()
