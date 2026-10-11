"""Conversation contracts on a real database using the restricted hosted writer."""
import pytest

from tests.postgresql.test_workflow_persistence import studio as studio_fixture
from tests.integration import test_conversations as acceptance
from tests.integration import test_chat_settings as settings_acceptance
from tests.integration import test_conversation_crud as crud
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


def test_chat_rename_and_duplicate_requests(chat_studio):
    crud.test_rename_read_refresh_multiturn_and_duplicates(chat_studio)


def test_chat_delete_retention_and_old_id(chat_studio):
    crud.test_delete_retains_governance_and_permanently_denies_old_id(chat_studio)


def test_chat_inflight_delete_settles_usage(chat_studio):
    crud.test_inflight_delete_settles_usage_without_resurrection(chat_studio)


def test_chat_unknown_usage_retained_after_delete(chat_studio):
    crud.test_unknown_run_retains_reservation_after_delete(chat_studio)


def test_chat_concurrent_metadata_duplicate(chat_studio):
    crud.test_concurrent_duplicate_rename_has_one_receipt(chat_studio)


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_chat_metadata_scope_and_permission(chat_studio, method):
    crud.test_csrf_origin_permissions_and_ownership(chat_studio, method)


@pytest.mark.parametrize("extra", [{"title": " "}, {"title": "x" * 121}, {"title": "Two\nlines"},
    {"actor_id": "forged"}, {"expected_metadata_revision": True}])
def test_chat_metadata_strict_validation(chat_studio, extra):
    crud.test_patch_strict_validation_does_not_mutate(chat_studio, extra)


def test_chat_metadata_guards_and_signed_head(postgres_db, chat_studio):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    client, db, _, _ = chat_studio
    identifier, _ = crud.start(chat_studio)
    assert client.request("DELETE", crud.CHAT + "/" + identifier, json=crud.intent()).status_code == 200
    for sql in ("UPDATE chat_conversation_changes SET title='forged'", "DELETE FROM chat_conversation_changes", "TRUNCATE chat_conversation_changes"):
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(sql))
    with pytest.raises(RuntimeError, match="tombstones"):
        migrate_to(postgres_db.owner, "022_chat_preferences", downgrade=True)
    # Deliberate owner-level rollback cannot roll back the independent Core head.
    with postgres_db.owner.begin() as connection:
        connection.execute(text("ALTER TABLE chat_conversation_changes DISABLE TRIGGER USER"))
        connection.execute(text("DELETE FROM chat_conversation_changes"))
        connection.execute(text("ALTER TABLE chat_conversation_changes ENABLE TRIGGER USER"))
    assert client.get(crud.CHAT + "/" + identifier).status_code == 503
    assert client.get(crud.CHAT).status_code == 503
