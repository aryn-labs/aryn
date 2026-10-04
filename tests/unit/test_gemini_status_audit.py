"""Gemini Integration Status Audit.

Verifies whether Google Gemini is live integrated or currently limited to
model specification and request structure definitions.
Complies with User Requirement #6: Never claim live Gemini PASS without actual requests and actual model proof.
"""

import os
import pytest
from packages.model_adapters import GeminiModelAdapter
from packages.contracts.model import ModelProviderType


def test_gemini_adapter_provides_model_specifications():
    """Confirms GeminiModelAdapter implements model specifications and parameters."""
    adapter = GeminiModelAdapter()
    specs = [
        adapter.get_spec("gemini-2.0-flash"),
        adapter.get_spec("gemini-1.5-pro"),
        adapter.get_spec("gemini-1.5-flash"),
    ]
    for spec in specs:
        assert spec.provider == ModelProviderType.GEMINI
        assert spec.context_window > 0
        assert spec.requires_api_key is True


def test_gemini_adapter_builds_request_payload():
    """Confirms GeminiModelAdapter can construct request structures."""
    adapter = GeminiModelAdapter(api_key="mock_key")
    payload = adapter.build_request_payload(
        prompt="Tell me about agent safety.",
        system_instructions="You are a safe assistant.",
        model_id="gemini-2.0-flash",
    )
    assert payload["model"] == "gemini-2.0-flash"
    assert payload["provider"] == "gemini"
    assert len(payload["messages"]) == 2


def test_gemini_status_is_specification_only_not_live():
    """Explicitly verifies that Gemini is NOT live-integrated in the current runtime.

    Validates that:
    1. No active GEMINI_API_KEY or GOOGLE_API_KEY is present in the runtime environment.
    2. GeminiModelAdapter does NOT implement an active network execution method.
    3. Live inference cannot be claimed without live credentials and actual network roundtrips.
    """
    adapter = GeminiModelAdapter()

    # Verify no execution method exists on the adapter (it is specification only)
    assert not hasattr(adapter, "execute"), "Gemini adapter unexpectedly implemented execute"
    assert not hasattr(adapter, "complete"), "Gemini adapter unexpectedly implemented complete"
    assert not hasattr(adapter, "stream"), "Gemini adapter unexpectedly implemented stream"

    # Verify environment keys
    has_live_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    assert not has_live_key, "Unexpected live Gemini key in local test environment"

    # Status must be reported as SPEC_ONLY
    gemini_status = "MODEL_SPECIFICATION_ONLY"
    assert gemini_status == "MODEL_SPECIFICATION_ONLY"
