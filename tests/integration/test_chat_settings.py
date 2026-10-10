"""Consent requires explicit, scoped server receipts before any model call."""
import copy

from database.schema import ProviderConsentModel, StudioPreferenceModel
from tests.integration.test_studio_api import studio as studio_fixture, PREFIX, DEV_ACTOR, DEV_ORG, DEV_PROJECT
from tests.integration.test_conversations import payload, complete, CHAT

settings_studio = studio_fixture

POLICIES = PREFIX + "/chat/provider-consent"
PREFERENCES = PREFIX + "/chat/preferences"


def grant(client):
    policy = client.get(POLICIES).json()["models"]["test/model-a"]
    result = client.post(POLICIES, json={"model": "test/model-a", "policy": policy["policy"]})
    assert result.status_code == 200, result.text
    return policy


def test_first_use_is_persistent_not_a_browser_boolean(settings_studio):
    client, db, runtime, app = settings_studio
    policy = client.get(POLICIES).json()["models"]["test/model-a"]
    assert policy["remote"] and not policy["consented"] and not runtime.requests
    assert client.post(CHAT, json=payload()).status_code == 422
    assert not runtime.requests
    grant(client)
    # Legacy flags are accepted for wire compatibility, but never grant authority.
    request = {**payload(), "allow_remote_model": False}
    identifier = client.post(CHAT, json=request).json()["id"]
    assert complete(client, identifier)["status"] == "completed"
    assert client.get(POLICIES).json()["models"]["test/model-a"]["consented"]
    from modules.core.conversations import Conversations
    service = Conversations(app.state.coordinator, app.state.conversations.catalog, app.state.conversations.require_runtime)
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    service.settings.require(ctx, "test/model-a")
    assert len(runtime.requests) == 1


def test_decline_forged_policy_authority_and_csrf_never_dispatch(settings_studio):
    client, _, runtime, _ = settings_studio
    policy = client.get(POLICIES).json()["models"]["test/model-a"]
    assert client.post(POLICIES, json={"model": "test/model-a", "policy": "a" * 64}).status_code == 409
    assert client.post(POLICIES, json={"model": "test/model-a", "policy": policy["policy"], "actor_id": "other"}).status_code == 422
    assert client.post(POLICIES, json={"model": "unknown", "policy": policy["policy"]}).status_code == 422
    assert client.post(POLICIES, json={"model": "test/model-a", "policy": policy["policy"]}, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert not client.get(POLICIES).json()["models"]["test/model-a"]["consented"]
    assert not runtime.requests


def test_revoke_blocks_future_calls_and_preserves_history(settings_studio):
    client, _, runtime, _ = settings_studio
    policy = grant(client)
    identifier = client.post(CHAT, json=payload()).json()["id"]
    complete(client, identifier)
    assert client.delete(POLICIES + "/" + policy["provider_id"]).status_code == 200
    follow = {**payload(), "idempotency_key": "follow-after-revocation", "expected_revision": 1}
    assert client.post(CHAT + "/" + identifier + "/messages", json=follow).status_code == 422
    assert len(client.get(CHAT + "/" + identifier).json()["messages"]) == 2
    assert len(runtime.requests) == 1
    grant(client)
    assert client.post(CHAT + "/" + identifier + "/messages", json=follow).status_code == 202
    assert complete(client, identifier)["revision"] == 2


def test_consent_replay_tampering_or_deletion_fails_closed(settings_studio):
    client, db, runtime, _ = settings_studio
    policy = grant(client)
    with db.session() as session:
        row = session.query(ProviderConsentModel).one()
        snapshot = {field: copy.deepcopy(getattr(row, field)) for field in ("policy", "granted_at", "revoked_at", "attestation")}
    client.delete(POLICIES + "/" + policy["provider_id"])
    with db.session(write=True) as session:
        session.query(ProviderConsentModel).update(snapshot)
    assert client.get(POLICIES).status_code == 503
    assert client.post(CHAT, json=payload()).status_code == 503
    assert not runtime.requests


def test_policy_or_gateway_route_change_requires_reconsent(settings_studio, monkeypatch):
    client, _, runtime, _ = settings_studio
    grant(client)
    monkeypatch.setattr("modules.core.chat_settings.POLICY_VERSION", "new-material-transfer-policy")
    assert not client.get(POLICIES).json()["models"]["test/model-a"]["consented"]
    assert client.post(CHAT, json=payload()).status_code == 422
    assert not runtime.requests


def test_language_defaults_persists_and_rejects_extra_authority(settings_studio):
    client, db, runtime, _ = settings_studio
    assert client.get(PREFERENCES).json()["locale"] == "id-ID"
    assert client.patch(PREFERENCES, json={"locale": "en-US"}).json()["locale"] == "en-US"
    assert client.get(PREFERENCES).json()["locale"] == "en-US"
    assert client.patch(PREFERENCES, json={"locale": "fr-FR"}).status_code == 422
    assert client.patch(PREFERENCES, json={"locale": "id-ID", "actor_id": "another"}).status_code == 422
    assert client.patch(PREFERENCES, json={"locale": "id-ID"}, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    with db.session() as session:
        assert session.query(StudioPreferenceModel).one().actor_id == DEV_ACTOR
    assert not runtime.requests


def test_other_authorized_person_project_and_organization_do_not_inherit_consent(settings_studio):
    client, db, _, app = settings_studio
    grant(client)
    from database.repositories.organization_repo import OrganizationRepository
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.add_member(DEV_ORG, "other-person", role="admin")
        repo.create_project(app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "another-project"), "another-project", "Another", "another")
        repo.create_organization("another-org", "Another", "another-org")
        repo.add_member("another-org", DEV_ACTOR, role="admin")
        repo.create_project(app.state.binder.create_trusted_context(DEV_ACTOR, "another-org", "another-project-org"), "another-project-org", "Another", "another")
    from modules.core.conversations import ChatError
    import pytest
    for actor, org, project in [("other-person", DEV_ORG, DEV_PROJECT), (DEV_ACTOR, DEV_ORG, "another-project"), (DEV_ACTOR, "another-org", "another-project-org")]:
        ctx = app.state.binder.create_trusted_context(actor, org, project)
        with pytest.raises(ChatError, match="remote_consent_required"):
            app.state.conversations.settings.require(ctx, "test/model-a")
    assert client.delete(POLICIES + "/foreign").status_code == 404
