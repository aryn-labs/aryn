"""Hosted authenticated ingress over live restricted PostgreSQL, never SQLite fallback."""

import pytest
from tests.security.test_deployment_authentication import hosted as hosted, ORIGIN
from tests.security.test_automation_webhook import ingress_hosted as ingress_hosted
from tests.security import test_automation_webhook as acceptance

pytestmark = pytest.mark.postgresql


@pytest.fixture(autouse=True)
def configured_ingress(monkeypatch):
    monkeypatch.setenv("ARYN_WEBHOOK_INGRESS_ORIGIN", ORIGIN)


@pytest.mark.parametrize("hosted", ["postgresql"], indirect=True)
@pytest.mark.parametrize("scenario", ["delivery", "rotation", "contention"])
def test_webhook_signed_persistence_and_admission(ingress_hosted, hosted, scenario):
    tests = {
        "delivery": acceptance.test_authenticated_https_creates_once_uses_reviewed_input_and_no_secret_read,
        "rotation": acceptance.test_rotation_revocation_pause_edit_and_rate_limits,
        "contention": acceptance.test_concurrent_signal_commits_one_occurrence_and_revoked_owner_denied,
    }
    tests[scenario](ingress_hosted)
