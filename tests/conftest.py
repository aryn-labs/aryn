"""Global Pytest Configuration and Security Fixtures for ARYN Test Suite.

Enforces explicit cryptographic secrets for development and test execution.
Strictly prohibits default or hardcoded secrets in production source files.
"""

from __future__ import annotations

import os
import pytest
from typing import Generator

from modules.core.identity.binder import TrustedIdentityBinder
from packages.contracts.core import SecurityContext

TEST_IDENTITY_SECRET = "aryn-test-explicit-entropy-secret-key-32b-secure"


def pytest_collection_modifyitems(items):
    """A normal regression run must never submit a live model request."""
    model_tests = {
        "test_live_end_to_end_smoke",
        "test_live_hermes_assigned_research_agent_run",
        "test_live_hermes_run_lifecycle_and_cancellation",
    }
    if os.getenv("ARYN_RUN_LIVE_MODEL_TESTS") != "1":
        for item in items:
            if item.name in model_tests:
                item.add_marker(pytest.mark.skip(reason="Live model tests require explicit opt-in after owner authorization."))


@pytest.fixture(autouse=True)
def setup_test_identity_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Ensures an explicit test identity secret is configured for all tests.
    
    Guarantees no component attempts to use a hardcoded default secret.
    """
    monkeypatch.setenv("ARYN_IDENTITY_SECRET", TEST_IDENTITY_SECRET)
    yield


@pytest.fixture
def identity_binder() -> TrustedIdentityBinder:
    """Provides a trusted identity binder initialized with an explicit test secret."""
    return TrustedIdentityBinder(secret_key=TEST_IDENTITY_SECRET)


def bind_test_context(
    context: SecurityContext,
    binder: TrustedIdentityBinder | None = None,
    secret_key: str | None = None,
) -> SecurityContext:
    """Helper for tests to bind authoritative identity tokens onto test SecurityContext instances."""
    active_binder = binder or TrustedIdentityBinder(secret_key=secret_key or TEST_IDENTITY_SECRET)
    return active_binder.bind_context(context)
