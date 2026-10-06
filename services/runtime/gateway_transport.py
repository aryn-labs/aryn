"""Hermes SDK transport restriction and evidence capture, independently testable."""

import json
from dataclasses import dataclass, field

import httpx

from packages.model_adapters.gateway import GatewaySettings, MODEL_ID


@dataclass
class ModelReceipt:
    requested_model: str
    actual_model: str | None = None
    provider: str | None = None
    failure: str | None = None
    verified: bool = False
    transport: object = field(default=None, repr=False)

    def evidence(self):
        if not self.verified or self.failure or self.actual_model != self.requested_model:
            return None
        return {"gateway": "9Router", "runtime_backend": "Hermes",
                "requested_model": self.requested_model, "actual_model": self.actual_model,
                "actual_model_source": "gateway_response", "provider": self.provider}


class ExactGatewayTransport(httpx.BaseTransport):
    """No alternate URLs, model substitutions, redirects, streaming or provider credentials.

    A rejection latches for the turn: Hermes retries cannot dispatch another model request.
    This wraps Hermes' OpenAI SDK transport, never executes the model instead of Hermes.
    """

    def __init__(self, settings: GatewaySettings, receipt: ModelReceipt, transport=None):
        self.settings, self.receipt = settings, receipt
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
                or body.get("stream") is True or body.get("tools") or body.get("functions")):
            return self._reject(request, "gateway_route_mismatch")
        # Strip all SDK/config headers. Only the optional gateway credential is forwarded.
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self.settings.api_key.get_secret_value()
        if key and key in json.dumps(body, ensure_ascii=False):
            return self._reject(request, "gateway_secret_leak")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        forwarded = httpx.Request("POST", request.url, headers=headers, content=request.content)
        try:
            response = self.inner.handle_request(forwarded)
            response.read()
        except httpx.HTTPError:
            return self._reject(request, "gateway_unreachable")
        if response.status_code != 200:
            # No upstream error body/header ever enters Hermes logs or an ARYN response.
            rejected = response.status_code == 404
            if response.status_code == 400:
                try:
                    error = response.json().get("error", {})
                    code = error.get("code", "") if isinstance(error, dict) else ""
                    message = error.get("message", "") if isinstance(error, dict) else ""
                    message = message.lower() if isinstance(message, str) else ""
                    rejected = code in {"model_not_found", "model_not_available", "unknown_model"} or (
                        "model" in message and any(p in message for p in ("not found", "not available", "does not exist", "unknown model")))
                except (ValueError, AttributeError):
                    pass
            response.close()
            return self._reject(request, "model_not_available" if rejected else "gateway_rejected")
        try:
            data = response.json()
            actual = data.get("model")
            if not isinstance(actual, str) or actual != self.receipt.requested_model:
                return self._reject(request, "actual_model_mismatch")
            if key and key in json.dumps(data, ensure_ascii=False):
                return self._reject(request, "gateway_secret_leak")
            provider = data.get("provider")
            self.receipt.provider = provider if isinstance(provider, str) and MODEL_ID.fullmatch(provider) else None
            self.receipt.actual_model, self.receipt.verified = actual, True
            choices = data.get("choices")
            usage = data.get("usage")
            if (not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict)
                    or choices[0].get("finish_reason") != "stop"
                    or not isinstance(choices[0].get("message"), dict)
                    or not isinstance(choices[0]["message"].get("content"), str)
                    or choices[0]["message"].get("tool_calls")
                    or not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                    or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
                return self._reject(request, "invalid_gateway_completion")
            safe = {"id": data.get("id"), "object": "chat.completion", "model": actual,
                    "created": data.get("created", 0), "usage": {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": choices[0]["message"]["content"]}}]}
            return httpx.Response(200, request=request, json=safe)
        except (ValueError, AttributeError, TypeError):
            return self._reject(request, "missing_gateway_provenance")
        finally:
            response.close()

    def close(self):
        self.inner.close()
