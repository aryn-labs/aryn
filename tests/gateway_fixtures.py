"""Explicit HTTP transport double shared by gateway security tests."""
import httpx
import time
from packages.model_adapters.gateway import GatewaySettings, NineRouterGateway
from packages.runtime_adapters import HermesRuntimeAdapter

MODEL = "test/model-a"
BASE = "http://127.0.0.1:20128/v1"
PROOF = {"gateway": "9Router", "runtime_backend": "Hermes", "requested_model": MODEL,
         "actual_model": MODEL, "actual_model_source": "gateway_response"}
COMPLETION = {"id": "isolated-runtime-id", "model": MODEL, "created": 1,
              "choices": [{"message": {"content": "Isolated output"}, "finish_reason": "stop"}],
              "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}, "aryn": PROOF}


def standard_handler(request, *, models=None, response=None):
    if request.url.port == 20128:
        rows = models if models is not None else [{"id": MODEL, "availability": "available"}]
        rows = [{**m, **({"availability_verified": True, "availability_source": "provider_discovery",
                         "availability_checked_at": time.time()} if m.get("availability") == "available" else {})} for m in rows]
        return httpx.Response(200, json={"object": "list", "data": rows})
    if request.url.path == "/v1/toolsets":
        return httpx.Response(200, json={"data": []})
    if request.url.path == "/aryn/gateway":
        return httpx.Response(200, json={"gateway": "9Router", "runtime_backend": "Hermes", "base_url": BASE,
                              "exact_model_enforced": True, "async_provenance": True})
    return httpx.Response(200, json=response or COMPLETION)


def make_adapter(client, *, secret=""):
    gateway = NineRouterGateway(GatewaySettings(api_key=secret), http_client=client)
    return HermesRuntimeAdapter(api_key="isolated-runtime-auth", http_client=client, model_gateway=gateway)
