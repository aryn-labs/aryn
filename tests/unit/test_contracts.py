"""Unit tests for ARYN contracts."""

import pytest
from packages.contracts.core import (
    Actor,
    ActorType,
    AuditEvent,
    AuditStatus,
    BudgetRule,
    PolicyDecision,
    SecurityContext,
)
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeCapabilities,
    RuntimeHealth,
)
from packages.contracts.model import ModelProviderType, ModelSpec


def test_security_context_ownership_validation():
    actor = Actor(actor_id="user_1", actor_type=ActorType.USER, organization_id="org_alpha")
    context = SecurityContext(actor=actor, organization_id="org_alpha", project_id="proj_x")

    assert context.validate_ownership("org_alpha", "proj_x") is True
    assert context.validate_ownership("org_beta", "proj_x") is False
    assert context.validate_ownership("org_alpha", "proj_y") is False


def test_audit_event_integrity_hash():
    event = AuditEvent(
        event_type="test.event",
        organization_id="org_1",
        project_id="proj_1",
        actor_type="user",
        actor_id="usr_123",
        correlation_id="corr_abc",
        resource_id="res_xyz",
        status=AuditStatus.ALLOWED,
        redacted_payload={"action": "test"},
    )
    sig1 = event.calculate_integrity()
    sig2 = event.calculate_integrity()

    assert sig1 == sig2
    assert len(sig1) == 64  # SHA256 hex string


def test_runtime_contracts_instantiation():
    req = RunRequest(prompt="Hello", model="test-model")
    assert req.prompt == "Hello"
    assert req.timeout_seconds == 30.0

    res = RunResult(
        run_id="run_1",
        status=RunStatus.COMPLETED,
        output="Result",
        usage=RunUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        model="test-model",
        created_at=100.0,
    )
    assert res.status == RunStatus.COMPLETED
    assert res.usage.total_tokens == 15


def test_model_spec_contract():
    spec = ModelSpec(
        provider=ModelProviderType.GEMINI,
        model_id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        context_window=1048576,
    )
    assert spec.provider == ModelProviderType.GEMINI
    assert spec.context_window == 1048576
