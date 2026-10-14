"""Read-only server-side 9Router discovery. No model/provider API invocation."""

import asyncio
import hashlib
import json
import re
import time

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from packages.contracts.runtime import GatewayDiscovery, RuntimeModelAvailability

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,127}$")


def model_presentation_metadata(model):
    """Ignore rich metadata containing secret fields, without inspecting their values."""
    pending = [model]
    visited = 0
    while pending:
        item = pending.pop()
        visited += 1
        if visited > 256:
            return {"id": model["id"]}
        if isinstance(item, dict):
            for key, value in item.items():
                if re.search(r"api.?key|secret|password|auth.?token|^auth$|^authorization$|credential|bearer|access.?token|refresh.?token|id.?token", key, re.I):
                    return {"id": model["id"]}
                if isinstance(value, (dict, list)):
                    pending.append(value)
        elif isinstance(item, list):
            pending.extend(value for value in item if isinstance(value, (dict, list)))
    return model


def model_display_name(model):
    """Presentation only. Known gateway route tokens confer no provider authority."""
    model = model_presentation_metadata(model)
    mid = model["id"]
    label = model.get("display_name", model.get("name"))
    if (isinstance(label, str) and label != mid and len(label) <= 128
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", label)):
        return label
    parts = mid.split("/")
    if len(parts) == 2 and parts[0] in {"ds", "ag", "cx", "gemini", "openai"} and parts[1]:
        name = parts[1]
    elif len(parts) == 1:
        name = mid
    else:
        # Unknown namespaces and multi-part IDs are not assumed to be route prefixes.
        return mid
    words = {"deepseek": "DeepSeek", "gemini": "Gemini", "gpt": "GPT", "claude": "Claude", "oss": "OSS"}
    return " ".join(words.get(word, word.capitalize() if word.islower() else word)
        for word in name.split("-"))


def disambiguate_model_names(rows):
    counts = {}
    for row in rows:
        label = row["display_name"]
        counts[label.casefold()] = counts.get(label.casefold(), 0) + 1
    for row in rows:
        if counts[row["display_name"].casefold()] > 1:
            row["display_name"] += " [" + row["model_id"] + "]"


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

    @property
    def configuration_id(self):
        # Bind credentials without persisting or disclosing their value.
        return hashlib.sha256(json.dumps(["aryn-gateway", self.base_url,
            self.api_key.get_secret_value()], separators=(",", ":")).encode()).hexdigest()

    def runtime_configuration_id(self, instance):
        return hashlib.sha256((self.configuration_id + ":" + instance).encode()).hexdigest()

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
        self._tool_probes = {}
        self._provider_configurations = {}
        self._provider_identities = {}
        self._runtime_configuration = None

    def bind_runtime_configuration(self, configuration):
        if configuration != self._runtime_configuration:
            self._tool_probes.clear()
        self._runtime_configuration = configuration

    @property
    def has_tool_verifications(self):
        return bool(self._tool_probes)

    def invalidate_tool_verification(self, model):
        self._tool_probes.pop(model, None)

    def _verified_tool_probe(self, model):
        entry = self._tool_probes.get(model)
        if entry is None:
            return None
        evidence, attestation, verifier = entry
        binding = evidence.binding
        if (model in self._rejected or not evidence.live_eligible
                or not 0 <= time.time() - evidence.observed_at <= 60
                or not evidence.observed_at < evidence.expires_at <= evidence.observed_at + 60
                or time.time() >= evidence.expires_at
                or binding.gateway_configuration != self.settings.configuration_id
                or binding.runtime_configuration != self._runtime_configuration
                or binding.provider_configuration != self._provider_configurations.get(model)
                or evidence.provider != self._provider_identities.get(model)
                or not verifier.verify("model_capability_probe", evidence.model_dump(mode="json"), attestation)):
            self._tool_probes.pop(model, None)
            return None
        return evidence

    def record_tool_verification(self, evidence, attestation, verifier):
        """Internal Core receipt. No browser/provider can supply the signing authority."""
        from packages.contracts.model import ModelProbeEvidence
        evidence = ModelProbeEvidence.model_validate(evidence)
        if self.client is not None or not evidence.live_eligible or not verifier.verify(
                "model_capability_probe", evidence.model_dump(mode="json"), attestation):
            return False
        if len(self._tool_probes) >= 128:
            self._tool_probes.pop(next(iter(self._tool_probes)))
        self._tool_probes[evidence.model] = evidence, attestation, verifier
        return self._verified_tool_probe(evidence.model) is not None

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
        if self._verified_tool_probe(model) is not None:
            return ModelCapabilities(model=model, text_generation="supported", tool_calling="supported",
                structured_output="supported", source="core_tool_probe_fixture")
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
        self._tool_probes.pop(model, None)

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
                    self._provider_configurations.clear()
                    self._provider_identities.clear()
                    for model in body["data"]:
                        if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not MODEL_ID.fullmatch(model["id"]):
                            raise ValueError("Invalid model identity")
                        mid = model["id"]
                        presentation = model_presentation_metadata(model)
                        provider = presentation.get("provider")
                        if (isinstance(provider, str) and MODEL_ID.fullmatch(provider)
                                and provider.lower() not in {"9router", "hermes", "unknown", "unavailable", "custom", "combo"}):
                            self._provider_identities[mid] = provider
                        revision = model.get("provider_configuration")
                        if isinstance(revision, str) and re.fullmatch(r"[a-f0-9]{64}", revision):
                            self._provider_configurations[mid] = revision
                        # A listing or a supports_tools boolean is never proof.
                        from packages.contracts.model import ModelCapabilities
                        observed_caps = model.get("capabilities_checked_at")
                        if (model.get("capabilities_verified") is True
                                and mid in self._provider_identities and mid in self._provider_configurations
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
                        if status == "unknown" and self._verified_tool_probe(mid) is not None:
                            status, reason = "available", "core_tool_probe_verified"
                        if model.get("owned_by") == "combo" or model.get("kind", "llm") != "llm":
                            status, reason = "unavailable", "non_exact_route"
                        if mid in self._rejected:
                            status, reason = "unavailable", "provider_rejected"
                        if status == "unavailable" and reason == "gateway_catalog_only":
                            reason = "not_offered_by_gateway"
                        if status == "unavailable":
                            self._tool_probes.pop(mid, None)
                        label = model_display_name(presentation)
                        provider = self._provider_identities.get(mid)
                        if key and (key in label or provider and key in provider):
                            raise ValueError("Protected credential in metadata")
                        # Only bounded presentation/status metadata crosses the boundary.
                        # owned_by may be a route alias, never infer provider identity from it.
                        reachable_at = model.get("provider_reachability_checked_at")
                        reachable = model.get("provider_reachability")
                        if (reachable not in {"reachable", "unreachable"}
                                or model.get("provider_reachability_verified") is not True
                                or model.get("provider_reachability_source") != "provider_discovery"
                                or type(reachable_at) not in {int, float}
                                or not 0 <= time.time() - reachable_at <= 60):
                            reachable = "unknown"
                        rows.append({"model_id": mid, "display_name": label, "gateway": "9Router", "provider": provider or "9router",
                                     "provider_identity_status": "reported" if provider else "unknown", "listed": True,
                                     "provider_configured": "configured" if model.get("provider_configured") is True else "unconfigured" if model.get("provider_configured") is False else "unknown",
                                     "provider_reachability": reachable, "credit_status": "unknown", "rate_limit_status": "unknown",
                                     "availability": status, "availability_reason": reason,
                                     "availability_source": "core_runtime_probe" if reason in {"core_runtime_verified", "core_tool_probe_verified"} else "9router_discovery"})
                    disambiguate_model_names(rows)
                    self._snapshot = GatewayDiscovery(connected=True, discovery_valid=True, reason="discovered", models=rows)
            except (httpx.HTTPError, ValueError, TypeError):
                self._snapshot = GatewayDiscovery(reason="discovery_unavailable")
            finally:
                if not self._snapshot.discovery_valid:
                    self._runtime_verified.clear()
                    self._capability_evidence.clear()
                    self._tool_probes.clear()
                    self._provider_configurations.clear()
                    self._provider_identities.clear()
                else:
                    current = {row["model_id"] for row in self._snapshot.models}
                    self._runtime_verified = {key: value for key, value in self._runtime_verified.items()
                        if key in current and 0 <= time.time() - value <= 60}
                    self._tool_probes = {key: value for key, value in self._tool_probes.items() if key in current}
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
        if row.get("availability_reason") == "core_tool_probe_verified" and self._verified_tool_probe(model) is None:
            return RuntimeModelAvailability(model=model, source="core_runtime_probe", reason="probe_evidence_unavailable")
        return RuntimeModelAvailability(model=model, status=row["availability"], source=row["availability_source"], reason=row["availability_reason"])
