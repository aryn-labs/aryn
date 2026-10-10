"""Conversation contracts on a real database using the restricted hosted writer."""
import pytest

from tests.postgresql.test_workflow_persistence import studio as studio_fixture
from tests.integration import test_conversations as acceptance
from tests.integration import test_chat_settings as settings_acceptance
from tests.postgresql.conftest import migrate_to

pytestmark = pytest.mark.postgresql
raw_studio = studio_fixture


@pytest.fixture
def chat_studio(raw_studio):
    client, db, runtime, app = raw_studio
    policy = client.get(acceptance.PREFIX + "/chat/provider-consent").json()["models"]["test/model-a"]
    assert client.post(acceptance.PREFIX + "/chat/provider-consent", json={"model": "test/model-a", "policy": policy["policy"]}).status_code == 200
    return client, db, runtime, app


def test_persistent_chat_and_idempotency(chat_studio):
    acceptance.test_persistent_multiturn_and_idempotency(chat_studio)


def test_unknown_chat_outcome_is_not_repeated(chat_studio):
    acceptance.test_unknown_outcome_cannot_be_reexecuted(chat_studio)


def test_chat_scope_and_actor_isolation(chat_studio):
    acceptance.test_authorized_foreign_project_and_user_cannot_read_history(chat_studio)


def test_chat_permission_revocation(chat_studio):
    acceptance.test_permission_csrf_scope_and_revocation(chat_studio)


def test_chat_consent_first_use_persistence(raw_studio):
    settings_acceptance.test_first_use_is_persistent_not_a_browser_boolean(raw_studio)


def test_chat_consent_rejection_before_dispatch(raw_studio):
    settings_acceptance.test_decline_forged_policy_authority_and_csrf_never_dispatch(raw_studio)


def test_chat_consent_revocation_and_regrant(raw_studio):
    settings_acceptance.test_revoke_blocks_future_calls_and_preserves_history(raw_studio)


def test_chat_consent_replayed_receipt_fails_closed(raw_studio):
    settings_acceptance.test_consent_replay_tampering_or_deletion_fails_closed(raw_studio)


def test_chat_consent_policy_change(raw_studio, monkeypatch):
    settings_acceptance.test_policy_or_gateway_route_change_requires_reconsent(raw_studio, monkeypatch)


def test_chat_language_is_personal_and_persistent(raw_studio):
    settings_acceptance.test_language_defaults_persists_and_rejects_extra_authority(raw_studio)


def test_chat_consent_scope_isolation(raw_studio):
    settings_acceptance.test_other_authorized_person_project_and_organization_do_not_inherit_consent(raw_studio)


def test_chat_populated_downgrade_refused(postgres_db, chat_studio):
    client, _, _, _ = chat_studio
    assert client.post(acceptance.CHAT, json=acceptance.payload()).status_code == 202
    with pytest.raises(RuntimeError, match="personal settings"):
        migrate_to(postgres_db.owner, "020_core_automations", downgrade=True)
