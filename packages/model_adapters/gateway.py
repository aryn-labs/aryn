"""Read-only server-side 9Router discovery. No model/provider API invocation."""

import asyncio
import re
import time

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from packages.contracts.runtime import GatewayDiscovery, RuntimeModelAvailability

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,127}$")


class GatewaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    base_url: str
    api_key: SecretStr

    @model_validator(mode="before")
    @classmethod
    def centralized_defaults(cls, values):
        from packages.config import get_settings
        values = dict(values)
        if "base_url" not in values or "api_key" not in values:
            settings = get_settings()
            values.setdefault("base_url", settings.nine_router_base_url)
            values.setdefault("api_key", settings.nine_router_api_key)
        return values

    def model_post_init(self, context):
        from packages.config import _validate_url
        object.__setattr__(self, "base_url", _validate_url(
            self.base_url, "ARYN_9ROUTER_BASE_URL", require_v1=True))

    @classmethod
    def from_env(cls):
        from packages.config import get_settings
        return get_settings().gateway_settings


class NineRouterGateway:
    def __init__(self, settings=None, *, http_client=None, timeout=5):
        self.settings = settings or GatewaySettings.from_env()
        self.client = http_client
        self.timeout = timeout
        self._snapshot = GatewayDiscovery()
        self._checked = 0.0
        self._lock = asyncio.Lock()
        self._rejected = set()
        self._runtime_verified = {}
        self._capability_evidence = {}

    async def model_capabilities(self, model):
        from packages.contracts.model import ModelCapabilities
        await self.discover(refresh=True)
        caps = self._capability_evidence.get(model, ModelCapabilities(model=model)).model_copy(deep=True)
        observed = self._runtime_verified.get(model)
        if observed is not None and model not in self._rejected and 0 <= time.time() - observed <= 60:
            caps.text_generation = "supported"
            if caps.source == "capability_evidence_unavailable":
                caps.source = "core_runtime_probe"
        if model in self._rejected:
            return ModelCapabilities(model=model, source="provider_rejected")
        return caps

    def record_runtime_verification(self, result):
        """Only Core-settled, measured, exact-model results establish readiness.

        This is a server-only boundary; no browser evidence or provider credentials.
        A probe does not authorize later execution: all normal admission gates remain.
        """
        if (not result.execution_claim_verified or result.status.value != "completed"
                or result.gateway != "9Router" or result.runtime_backend != "Hermes"
                or result.requested_model != result.model or result.actual_model != result.model
                or result.usage.availability != "measured" or result.completed_at is None
                or not 0 <= time.time() - result.completed_at <= 60):
            raise ValueError("Unverified Core model result")
        self._runtime_verified[result.model] = result.completed_at

    def reject(self, model):
        self._rejected.add(model)
        self._runtime_verified.pop(model, None)

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
                    self._capability_evidence.clear()
                    for model in body["data"]:
                        if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not MODEL_ID.fullmatch(model["id"]):
                            raise ValueError("Invalid model identity")
                        mid = model["id"]
                        # A listing or a supports_tools boolean is never proof.
                        from packages.contracts.model import ModelCapabilities
                        observed_caps = model.get("capabilities_checked_at")
                        if (model.get("capabilities_verified") is True
                                and model.get("capabilities_source") in {"provider_attestation", "runtime_probe"}
                                and type(observed_caps) in {int, float}
                                and 0 <= time.time() - observed_caps <= 60
                                and isinstance(model.get("capabilities"), dict)):
                            self._capability_evidence[mid] = ModelCapabilities(
                                model=mid, source=model["capabilities_source"], **model["capabilities"])
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
                        verified_at = self._runtime_verified.get(mid)
                        if (status == "unknown" and verified_at is not None
                                and 0 <= time.time() - verified_at <= 60):
                            status, reason = "available", "core_runtime_verified"
                        if model.get("owned_by") == "combo" or model.get("kind", "llm") != "llm":
                            status, reason = "unavailable", "non_exact_route"
                        if mid in self._rejected:
                            status, reason = "unavailable", "provider_rejected"
                        if status == "unavailable" and reason == "gateway_catalog_only":
                            reason = "not_offered_by_gateway"
                        # Raw labels, provider metadata and errors never cross the boundary.
                        rows.append({"model_id": mid, "display_name": mid, "gateway": "9Router", "provider": "9router",
                                     "availability": status, "availability_reason": reason,
                                     "availability_source": "core_runtime_probe" if reason == "core_runtime_verified" else "9router_discovery"})
                    self._snapshot = GatewayDiscovery(connected=True, discovery_valid=True, reason="discovered", models=rows)
            except (httpx.HTTPError, ValueError, TypeError):
                self._snapshot = GatewayDiscovery(reason="discovery_unavailable")
            finally:
                if not self._snapshot.discovery_valid:
                    self._runtime_verified.clear()
                    self._capability_evidence.clear()
                else:
                    current = {row["model_id"] for row in self._snapshot.models}
                    self._runtime_verified = {key: value for key, value in self._runtime_verified.items()
                        if key in current and 0 <= time.time() - value <= 60}
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
