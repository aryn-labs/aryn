"""AF-07: strict human intent contracts cannot carry client governance truth."""
import pytest
from pydantic import ValidationError
from packages.contracts.agent import RollbackIntent


def valid_intent():
    return dict(target_version_id="prior", expected_current_version_id="current", expected_transition_id="activation",
        reason="Restore previous verified publication.", idempotency_key="rollback-intent-key")


def test_rollback_intent_captures_reviewed_state_without_client_authority():
    intent = RollbackIntent(**valid_intent())
    assert intent.target_version_id == "prior" and intent.expected_transition_id == "activation"


@pytest.mark.parametrize("field,value", [("reason", " "), ("target_version_id", ""),
    ("expected_current_version_id", ""), ("idempotency_key", "short"), ("idempotency_key", "bad key with spaces"),
    ("known_good", True), ("verified", True), ("rollback_safe", True), ("approved", True), ("bench_passed", True)])
def test_invalid_or_forged_intent_rejected(field, value):
    body = valid_intent()
    body[field] = value
    with pytest.raises(ValidationError):
        RollbackIntent(**body)
