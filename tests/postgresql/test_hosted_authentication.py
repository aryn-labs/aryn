"""Run the existing signed-provider/API/Core assertions against the hosted role.

The provider has valid synthetic signatures; the persistence, session transactions
and Core authorization are real PostgreSQL, never a production IdP or provider.
"""
import pytest

from tests.security import test_deployment_authentication as boundary
from tests.security.test_deployment_authentication import hosted as hosted

pytestmark = pytest.mark.postgresql


@pytest.mark.parametrize("hosted", ["postgresql"], indirect=True)
@pytest.mark.parametrize("scenario", ["principal", "governance", "logout", "persistence", "role_change",
                                       "session", "membership", "identity", "expiry"])
def test_signed_hosted_authentication_uses_live_persistence(hosted, scenario):
    tests = {
        "principal": boundary.test_valid_subject_scoped_core_principal_and_no_browser_escalation,
        "governance": boundary.test_authenticated_hosted_governance_run_and_stream_use_core,
        "logout": boundary.test_csrf_logout_fixation_and_cross_browser_callback,
        "persistence": boundary.test_server_sessions_persist_without_development_fallback,
        "role_change": boundary.test_role_change_after_preflight_and_invalid_csrf_denied,
    }
    if scenario in tests:
        tests[scenario](hosted)
    else:
        boundary.test_revocation_and_expiry_rechecked_at_core_commit(hosted, scenario)
