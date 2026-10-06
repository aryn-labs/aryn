"""Read-only server-side 9Router discovery. No model/provider API invocation."""

import asyncio
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from packages.contracts.runtime import GatewayDiscovery, RuntimeModelAvailability

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,127}$")


class GatewaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    base_url: str = "http://127.0.0.1:20128/v1"
    api_key: SecretStr = SecretStr("")

    def model_post_init(self, context):
        url = urlsplit(self.base_url)
        if (url.scheme not in {"http", "https"} or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1"):
            raise ValueError("9Router must use a loopback /v1 endpoint without URL credentials.")

    @classmethod
    def from_env(cls):
        # Explicit allowlist: no dotenv scan, provider environment reads, or config DB access.
        return cls(base_url=os.getenv("ARYN_9ROUTER_BASE_URL", "http://127.0.0.1:20128/v1").rstrip("/"),
                   api_key=SecretStr(os.getenv("ARYN_9ROUTER_API_KEY", "")))


class NineRouterGateway:
    def __init__(self, settings=None, *, http_client=None, timeout=5):
        self.settings = settings or GatewaySettings.from_env()
        self.client = http_client
        self.timeout = timeout
        self._snapshot = GatewayDiscovery()
        self._checked = 0.0
        self._lock = asyncio.Lock()
        self._rejected = set()

    def reject(self, model):
        self._rejected.add(model)

    async def discover(self, *, refresh=False):
        async with self._lock:
            if not refresh and time.monotonic() - self._checked < 10:
                return self._snapshot.model_copy(deep=True)
            client = self.client or httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=self.timeout)
            headers = {"Accept": "application/json"}
            key = self.settings.api_key.get_secret_value()
            if key:
                headers["Authorization"] = f"Bearer {key}"
            try:
                response = await client.get(f"{self.settings.base_url}/models", headers=headers, timeout=self.timeout,
                                            follow_redirects=False)
                if response.status_code != 200:
                    self._snapshot = GatewayDiscovery(connected=True, reason="discovery_rejected")
                else:
                    body = response.json()
                    if not isinstance(body, dict) or body.get("object") != "list" or not isinstance(body.get("data"), list):
                        raise ValueError("Invalid discovery")
                    rows, seen = [], set()
                    for model in body["data"]:
                        if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not MODEL_ID.fullmatch(model["id"]):
                            raise ValueError("Invalid model identity")
                        mid = model["id"]
                        if key and key in mid:
                            raise ValueError("Protected credential in discovery")
                        if mid in seen:
                            raise ValueError("Ambiguous model identity")
                        seen.add(mid)
                        # 9Router may generate its list from static defaults. Listing is not proof.
                        status = model.get("availability", "unknown")
                        if status not in {"available", "unavailable", "unknown"}:
                            status = "unknown"
                        observed = model.get("availability_checked_at")
                        if status == "available" and (model.get("availability_verified") is not True
                                or model.get("availability_source") not in {"provider_discovery", "runtime_probe"}
                                or type(observed) not in {int, float} or not 0 <= time.time() - observed <= 60):
                            status = "unknown"
                        reason = "gateway_verified_availability" if status == "available" else "gateway_catalog_only"
                        if model.get("owned_by") == "combo" or model.get("kind", "llm") != "llm":
                            status, reason = "unavailable", "non_exact_route"
                        if mid in self._rejected:
                            status, reason = "unavailable", "provider_rejected"
                        if status == "unavailable" and reason == "gateway_catalog_only":
                            reason = "not_offered_by_gateway"
                        # Raw labels, provider metadata and errors never cross the boundary.
                        rows.append({"model_id": mid, "display_name": mid, "gateway": "9Router", "provider": "9router",
                                     "availability": status, "availability_reason": reason,
                                     "availability_source": "9router_discovery"})
                    self._snapshot = GatewayDiscovery(connected=True, discovery_valid=True, reason="discovered", models=rows)
            except (httpx.HTTPError, ValueError, TypeError):
                self._snapshot = GatewayDiscovery(reason="discovery_unavailable")
            finally:
                self._checked = time.monotonic()
                if self.client is None:
                    await client.aclose()
            return self._snapshot.model_copy(deep=True)

    async def availability(self, model, *, refresh=False):
        snapshot = await self.discover(refresh=refresh)
        if not snapshot.discovery_valid:
            return RuntimeModelAvailability(model=model, source="9router_discovery", reason=snapshot.reason)
        row = next((r for r in snapshot.models if r["model_id"] == model), None)
        if row is None:
            return RuntimeModelAvailability(model=model, status="unavailable", source="9router_discovery", reason="not_offered_by_gateway")
        return RuntimeModelAvailability(model=model, status=row["availability"], source=row["availability_source"], reason=row["availability_reason"])
