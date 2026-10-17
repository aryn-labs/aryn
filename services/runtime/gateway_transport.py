"""Hermes SDK transport restriction and evidence capture, independently testable."""

import json
import re
import threading
from dataclasses import dataclass, field

import httpx
from packages.contracts.bench import strict_json_loads
from packages.contracts.runtime import RunUsage, ToolCall
from packages.model_adapters.gateway import GatewaySettings, MODEL_ID


@dataclass
class ModelReceipt:
    requested_model: str
    actual_model: str | None = None
    reported_model: str | None = None
    response_fields: list[str] = field(default_factory=list)
    session_id: str | None = None
    provider: str | None = None
    failure: str | None = None
    verified: bool = False
    dispatched: bool = False
    dispatch_lock: object = field(default_factory=threading.Lock, repr=False)
    transport: object = field(default=None, repr=False)
    tool_names: tuple[str, ...] | None = None
    tool_declarations: tuple = ()
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: RunUsage | None = None
    evidence_origin: str = "unavailable"
    provider_configuration: str | None = None

    def evidence(self):
        if not self.verified or self.failure or self.actual_model != self.requested_model:
            return None
        return {"gateway": "9Router", "runtime_backend": "Hermes",
                "requested_model": self.requested_model, "actual_model": self.actual_model,
                "reported_model": self.reported_model,
                "actual_model_source": "gateway_response", "provider": self.provider}


class ExactGatewayTransport(httpx.BaseTransport):
    """No alternate URLs, model substitutions, redirects, streaming or provider credentials.

    A rejection latches for the turn: Hermes retries cannot dispatch another model request.
    This wraps Hermes' OpenAI SDK transport, never executes the model instead of Hermes.
    """

    def __init__(self, settings: GatewaySettings, receipt: ModelReceipt, transport=None):
        self.settings, self.receipt = settings, receipt
        receipt.evidence_origin = "isolated_test_double" if transport is not None else "gateway_response"
        self.inner = transport or httpx.HTTPTransport(retries=0, trust_env=False)

    def _reject(self, request, code):
        self.receipt.failure = code
        self.receipt.verified = False
        return httpx.Response(400, request=request, json={"error": {"code": code, "message": "Governed gateway request rejected."}})

    def handle_request(self, request):
        if self.receipt.failure:
            return self._reject(request, self.receipt.failure)
        try:
            body = json.loads(request.read())
        except (ValueError, TypeError):
            return self._reject(request, "invalid_gateway_request")
        if (str(request.url) != f"{self.settings.base_url}/chat/completions" or request.method != "POST"
                or not isinstance(body, dict) or body.get("model") != self.receipt.requested_model
                or body.get("stream") is True or body.get("functions")):
            return self._reject(request, "gateway_route_mismatch")
        if self.receipt.tool_names is None:
            if body.get("tools"):
                return self._reject(request, "gateway_route_mismatch")
        else:
            from packages.tool_adapters.fixture import NAME, definition
            if self.receipt.tool_declarations:
                from packages.contracts.tool import ToolDeclaration
                declarations = [ToolDeclaration.model_validate(value) for value in self.receipt.tool_declarations]
                if tuple(value.name for value in declarations) != self.receipt.tool_names:
                    return self._reject(request, "gateway_tool_schema_mismatch")
                expected = [value.definition() for value in declarations]
            else:
                expected = [definition()] if self.receipt.tool_names == (NAME,) else []
            if body.get("tools", []) != expected:
                return self._reject(request, "gateway_tool_schema_mismatch")
        with self.receipt.dispatch_lock:
            if self.receipt.dispatched:
                return self._reject(request, "additional_dispatch_forbidden")
            self.receipt.dispatched = True
        options = self.receipt.transport or {}
        cap = options.get("max_tokens")
        if type(cap) is int and cap > 0:
            body["max_tokens"] = min(cap, body.get("max_tokens", cap)) if type(body.get("max_tokens", cap)) is int else cap
        body.pop("max_completion_tokens", None)
        body.pop("n", None)
        body["stream"] = False
        # Strip all SDK/config headers. Only the optional gateway credential is forwarded.
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self.settings.api_key.get_secret_value()
        if key and key in json.dumps(body, ensure_ascii=False):
            return self._reject(request, "gateway_secret_leak")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        forwarded = httpx.Request("POST", request.url, headers=headers, content=json.dumps(body).encode())
        try:
            response = self.inner.handle_request(forwarded)
            response.read()
        except httpx.HTTPError:
            return self._reject(request, "gateway_unreachable")
        if response.status_code != 200:
            # No upstream error body/header ever enters Hermes logs or an ARYN response.
            rejected = response.status_code == 404
            code = ""
            try:
                error = response.json().get("error", {})
                code = error.get("code", "") if isinstance(error, dict) else ""
                code = code if isinstance(code, str) else ""
            except (ValueError, AttributeError):
                pass
            if response.status_code == 400:
                try:
                    error = response.json().get("error", {})
                    code = error.get("code", "") if isinstance(error, dict) else ""
                    code = code if isinstance(code, str) else ""
                    message = error.get("message", "") if isinstance(error, dict) else ""
                    message = message.lower() if isinstance(message, str) else ""
                    rejected = code in {"model_not_found", "model_not_available", "unknown_model"} or (
                        "model" in message and any(p in message for p in ("not found", "not available", "does not exist", "unknown model")))
                except (ValueError, AttributeError):
                    pass
            response.close()
            failure = ("provider_insufficient_credit" if code in {"insufficient_credit", "insufficient_balance"}
                else "provider_quota_exhausted" if code == "insufficient_quota"
                else "provider_rate_limited" if response.status_code == 429
                else "provider_unavailable" if response.status_code in {502, 503, 504}
                else "model_not_available" if rejected else "gateway_rejected")
            return self._reject(request, failure)
        try:
            raw_text = response.text
            if "data: [DONE]" in raw_text:
                raw_text = raw_text.split("data: [DONE]")[0].strip()
            data = strict_json_loads(raw_text)
            if isinstance(data, dict):
                self.receipt.response_fields = [name for name in data
                    if isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", name)][:16]
            if key and key in json.dumps(data, ensure_ascii=False):
                return self._reject(request, "gateway_secret_leak")
            actual = data.get("model")
            self.receipt.reported_model = actual if isinstance(actual, str) and MODEL_ID.fullmatch(actual) else None
            requested = self.receipt.requested_model
            # A routing prefix is not evidence of equivalent model identity.
            # No provider-specific alias can silently authorize a different response ID.
            model_matches = isinstance(actual, str) and actual == requested
            if not model_matches:
                return self._reject(request, "actual_model_mismatch")
            provider = data.get("provider")
            self.receipt.provider = provider if isinstance(provider, str) and MODEL_ID.fullmatch(provider) else None
            revision = data.get("provider_configuration")
            self.receipt.provider_configuration = revision if isinstance(revision, str) and re.fullmatch(r"[a-f0-9]{64}", revision) else None
            self.receipt.actual_model, self.receipt.verified = requested, True
            choices = data.get("choices")
            usage = data.get("usage")
            if (not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict)
                    or choices[0].get("finish_reason") not in {"stop", "tool_calls"}
                    or not isinstance(choices[0].get("message"), dict)
                    or not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                    or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
                return self._reject(request, "invalid_gateway_completion")
            self.receipt.usage = RunUsage(input_tokens=usage["prompt_tokens"],
                output_tokens=usage["completion_tokens"], total_tokens=usage["total_tokens"])
            message = choices[0]["message"]
            calls = message.get("tool_calls")
            if calls:
                if (self.receipt.tool_names is None or choices[0]["finish_reason"] != "tool_calls"
                        or not isinstance(calls, list) or not 1 <= len(calls) <= 32):
                    return self._reject(request, "invalid_gateway_completion")
                parsed = []
                for call in calls:
                    if (not isinstance(call, dict) or set(call) != {"id", "type", "function"}
                            or call["type"] != "function" or not isinstance(call["function"], dict)
                            or set(call["function"]) != {"name", "arguments"}
                            or not isinstance(call["function"]["arguments"], str)
                            or len(call["function"]["arguments"]) > 4096):
                        return self._reject(request, "invalid_tool_proposal")
                    parsed.append(ToolCall(call_id=call["id"], name=call["function"]["name"],
                        arguments=strict_json_loads(call["function"]["arguments"])))
                if len({call.call_id for call in parsed}) != len(parsed):
                    return self._reject(request, "duplicate_tool_proposal")
                self.receipt.tool_calls = parsed
                # Hermes' request worker swallows BaseException. A typed proposal
                # receipt plus an inert terminal marker ends its single turn safely;
                # the marker is never a final output or a successful Core run.
                return httpx.Response(200, request=request, json={"id": data.get("id"),
                    "object": "chat.completion", "model": requested, "created": data.get("created", 0),
                    "usage": {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {
                        "role": "assistant", "content": "ARYN_CORE_TOOL_PROPOSAL_PENDING"}}]})
            if choices[0]["finish_reason"] != "stop" or not isinstance(message.get("content"), str):
                return self._reject(request, "invalid_gateway_completion")
            safe = {"id": data.get("id"), "object": "chat.completion", "model": requested,
                    "created": data.get("created", 0), "usage": {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": choices[0]["message"]["content"]}}]}
            return httpx.Response(200, request=request, json=safe)
        except (ValueError, AttributeError, TypeError):
            return self._reject(request, "missing_gateway_provenance")
        finally:
            response.close()

    def close(self):
        self.inner.close()
