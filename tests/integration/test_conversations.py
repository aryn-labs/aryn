"""Offline contract tests; runtime fixtures are never evidence of real inference."""
import asyncio
import time

import pytest
from sqlalchemy import text
from database.schema import ConversationTurnModel, MembershipModel, UsageBudgetModel
from tests.integration.test_studio_api import studio as studio_fixture, PREFIX, DEV_ORG, DEV_ACTOR, DEV_PROJECT

raw_studio = studio_fixture


@pytest.fixture
def chat_studio(raw_studio):
    client, db, runtime, app = raw_studio
    policy = client.get(PREFIX + "/chat/provider-consent").json()["models"]["test/model-a"]
    assert client.post(PREFIX + "/chat/provider-consent", json={"model": "test/model-a", "policy": policy["policy"]}).status_code == 200
    return client, db, runtime, app

CHAT = PREFIX + "/chat/conversations"


def payload(**values):
    base = dict(message="Explain a simple concept", model="test/model-a",
        idempotency_key="chat-contract-request-001", allow_remote_model=True)
    base.update(values)
    return base


def complete(client, identifier):
    for _ in range(80):
        response = client.get(CHAT + "/" + identifier)
        assert response.status_code == 200, response.text
        if response.json()["status"] != "processing":
            return response.json()
        time.sleep(0.01)
    pytest.fail("Core did not finish the isolated test turn")


def test_persistent_multiturn_and_idempotency(chat_studio):
    client, db, runtime, app = chat_studio
    first = client.post(CHAT, json=payload())
    assert first.status_code == 202, first.text
    identifier = first.json()["id"]
    result = complete(client, identifier)
    assert result["status"] == "completed" and len(result["messages"]) == 2
    repeat = client.post(CHAT, json=payload())
    assert repeat.json()["id"] == identifier and len(runtime.requests) == 1
    changed = payload()
    changed["message"] = "different input"
    assert client.post(CHAT, json=changed).status_code == 409
    follow = payload()
    follow.update(message="Give me an example of that", idempotency_key="chat-contract-request-002", expected_revision=1)
    assert client.post(CHAT + "/" + identifier + "/messages", json=follow).status_code == 202
    final = complete(client, identifier)
    assert len(final["messages"]) == 4 and len(runtime.requests) == 2
    assert result["messages"][1]["content"] in runtime.requests[1].prompt
    assert runtime.requests[1].system_instructions == runtime.requests[0].system_instructions
    assert runtime.requests[1].session_id is None
    assert client.get(CHAT).json()["items"][0]["id"] == identifier
    with db.session() as session:
        budget = session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one()
        assert budget.cumulative_tokens == 100 and budget.reserved_tokens == 0
        assert session.execute(text("SELECT COUNT(*) FROM agent_assignments")).scalar() == 0
    # New service instance reuses persisted turns and Core results, without model calls.
    from modules.core.conversations import Conversations
    service = Conversations(app.state.coordinator, app.state.conversations.catalog, app.state.conversations.require_runtime)
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    from fastapi.encoders import jsonable_encoder
    assert jsonable_encoder(service.read(ctx, identifier)["messages"]) == final["messages"]


def test_conversation_model_can_be_changed_between_turns(chat_studio):
    client, db, runtime, app = chat_studio
    policy_b = client.get(PREFIX + "/chat/provider-consent").json()["models"]["test/model-b"]
    assert client.post(PREFIX + "/chat/provider-consent", json={"model": "test/model-b", "policy": policy_b["policy"]}).status_code == 200

    first = client.post(CHAT, json=payload(model="test/model-a"))
    assert first.status_code == 202
    identifier = first.json()["id"]
    res1 = complete(client, identifier)
    assert res1["model"] == "test/model-a"
    assert res1["messages"][1]["model"] == "test/model-a"

    follow = payload(model="test/model-b", message="Explain further with second model",
                     idempotency_key="chat-contract-request-switch", expected_revision=1)
    response = client.post(CHAT + "/" + identifier + "/messages", json=follow)
    assert response.status_code == 202
    res2 = complete(client, identifier)
    assert res2["model"] == "test/model-b"
    assert len(res2["messages"]) == 4
    assert res2["messages"][1]["model"] == "test/model-a"
    assert res2["messages"][3]["model"] == "test/model-b"


@pytest.mark.parametrize("extra", [{"system_instructions": "forged"}, {"tools": ["host"]}, {"role": "system"}, {"actor_id": "owner"}, {"message": " "}])
def test_rejects_authority_injection_and_missing_consent(chat_studio, extra):
    client, db, runtime, _ = chat_studio
    assert client.post(CHAT, json={**payload(), **extra}).status_code == 422
    assert not runtime.requests
    with db.session() as session:
        assert session.query(ConversationTurnModel).count() == 0


def test_permission_csrf_scope_and_revocation(chat_studio):
    client, db, runtime, app = chat_studio
    assert client.post(CHAT, json=payload(), headers={"X-CSRF-Token": "invalid"}).status_code == 403
    identifier = client.post(CHAT, json=payload()).json()["id"]
    complete(client, identifier)
    assert client.get("/api/projects/foreign/chat/conversations/" + identifier).status_code == 403
    ctx = app.state.binder.create_trusted_context("other-user", DEV_ORG, DEV_PROJECT)
    from modules.core.permissions.engine import PermissionDeniedError
    with pytest.raises(PermissionDeniedError):
        app.state.conversations.read(ctx, identifier)
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(user_id=DEV_ACTOR).update({"role": "viewer"})
    assert client.post(CHAT, json=payload()).status_code == 403
    assert client.get(PREFIX + "/chat/capability").status_code == 403


def test_model_and_budget_fail_closed(chat_studio):
    client, db, runtime, _ = chat_studio
    runtime.online = False
    assert client.post(CHAT, json=payload()).status_code == 503
    runtime.online = True
    with db.session(write=True) as session:
        session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).update({"max_tokens_per_run": 20})
    assert client.post(CHAT, json=payload()).status_code == 403
    assert not runtime.requests


def test_unknown_outcome_cannot_be_reexecuted(chat_studio):
    client, db, runtime, _ = chat_studio
    async def uncertain(request, context):
        runtime.requests.append(request)
        raise TimeoutError("never expose provider secret or traceback")
    runtime.execute_direct_turn = uncertain
    identifier = client.post(CHAT, json=payload()).json()["id"]
    result = complete(client, identifier)
    assert result["status"] == "outcome_unknown" and len(result["messages"]) == 1
    assert "secret" not in str(result)
    assert client.post(CHAT, json=payload()).status_code == 202
    follow = {**payload(), "idempotency_key": "different-contract-request", "expected_revision": 1}
    assert client.post(CHAT + "/" + identifier + "/messages", json=follow).status_code == 409
    assert len(runtime.requests) == 1
    with db.session() as session:
        assert session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one().reserved_tokens > 0


def test_inflight_duplicate_and_revision(chat_studio):
    client, _, runtime, _ = chat_studio
    original = runtime.execute_direct_turn
    async def delayed(request, context):
        await asyncio.sleep(0.15)
        return await original(request, context)
    runtime.execute_direct_turn = delayed
    identifier = client.post(CHAT, json=payload()).json()["id"]
    assert client.post(CHAT, json=payload()).json()["id"] == identifier
    stale = {**payload(), "idempotency_key": "new-request-stale-revision"}
    assert client.post(CHAT + "/" + identifier + "/messages", json=stale).status_code == 409
    complete(client, identifier)
    assert len(runtime.requests) == 1


def test_tampered_stored_transcript_is_rejected(chat_studio):
    client, db, _, _ = chat_studio
    identifier = client.post(CHAT, json=payload()).json()["id"]
    complete(client, identifier)
    with db.session(write=True) as session:
        session.query(ConversationTurnModel).update({"input": "forged history"})
    assert client.get(CHAT + "/" + identifier).status_code == 503


def test_authorized_foreign_project_and_user_cannot_read_history(chat_studio):
    client, db, _, app = chat_studio
    identifier = client.post(CHAT, json=payload()).json()["id"]
    complete(client, identifier)
    from database.repositories.organization_repo import OrganizationRepository
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "other-project")
        repo.create_project(ctx, "other-project", "Other", "other")
        repo.add_member(DEV_ORG, "other-user", role="admin")
        repo.create_organization("other-org", "Foreign", "foreign")
        repo.add_member("other-org", DEV_ACTOR, role="admin")
        repo.create_project(app.state.binder.create_trusted_context(DEV_ACTOR, "other-org", "foreign-project"), "foreign-project", "Foreign", "foreign")
    assert client.get("/api/projects/other-project/chat/conversations/" + identifier).status_code == 404
    from modules.core.conversations import ChatError
    for actor, org, project in [("other-user", DEV_ORG, DEV_PROJECT), (DEV_ACTOR, "other-org", "foreign-project")]:
        ctx = app.state.binder.create_trusted_context(actor, org, project)
        assert app.state.conversations.history(ctx)["items"] == []
        with pytest.raises(ChatError) as error:
            app.state.conversations.read(ctx, identifier)
        assert error.value.status == 404


def test_rate_limit_and_context_limit_keep_admission_atomic(chat_studio, monkeypatch):
    client, db, runtime, _ = chat_studio
    identifier = client.post(CHAT, json=payload()).json()["id"]
    complete(client, identifier)
    monkeypatch.setattr("modules.core.conversations.RATE_LIMIT", 1)
    next_request = {**payload(), "idempotency_key": "new-request-rate-limited"}
    assert client.post(CHAT, json=next_request).status_code == 429
    assert len(runtime.requests) == 1
    monkeypatch.setattr("modules.core.conversations.RATE_LIMIT", 12)
    with db.session(write=True) as session:
        session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).update({"max_turns": 1})
    next_request["expected_revision"] = 1
    assert client.post(CHAT + "/" + identifier + "/messages", json=next_request).status_code == 422
    assert len(runtime.requests) == 1


def test_unknown_model_and_enabled_tools_are_never_dispatched(chat_studio):
    client, _, runtime, _ = chat_studio
    assert client.post(CHAT, json={**payload(), "model": "unknown/model"}).status_code == 503
    runtime.tools = ["terminal"]
    assert client.post(CHAT, json=payload()).status_code == 503
    assert not runtime.requests


def test_chat_migration_is_additive_and_empty_roundtrip(tmp_path):
    from alembic import command
    from alembic.config import Config
    from database.connection import create_db_engine
    from sqlalchemy import inspect
    engine = create_db_engine("sqlite:///" + (tmp_path / "migration.sqlite3").as_posix())
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "020_core_automations")
        before = set(inspect(connection).get_table_names())
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) - before == {"chat_conversations", "chat_turns", "chat_provider_consents", "studio_preferences", "chat_conversation_changes", "project_mutations",
            "bench_suite_versions", "bench_scenario_candidates", "evidence_connections", "evidence_references",
            "brief_interpretations", "incident_capsules", "incident_capsule_replays"}
        command.downgrade(config, "020_core_automations")
        assert set(inspect(connection).get_table_names()) == before
        command.upgrade(config, "head")
    engine.dispose()


def test_shutdown_unknown_survives_application_restart_without_redispatch(chat_studio):
    from fastapi.testclient import TestClient
    from services.api.studio import create_app
    from tests.integration.test_studio_api import ORIGIN
    client, db, runtime, app = chat_studio

    async def interrupted(request, context):
        runtime.requests.append(request)
        await asyncio.sleep(30)

    runtime.execute_direct_turn = interrupted
    identifier = client.post(CHAT, json=payload()).json()["id"]
    client.portal.call(app.state.conversations.close)
    assert complete(client, identifier)["status"] == "outcome_unknown"
    restarted = create_app(db, runtime, testing=True)
    with TestClient(restarted, base_url=ORIGIN, client=("127.0.0.1", 2)) as resumed:
        token = resumed.post("/api/session", json={}, headers={"Origin": ORIGIN}).json()["csrf"]
        resumed.headers.update({"Origin": ORIGIN, "X-CSRF-Token": token})
        saved = resumed.get(CHAT + "/" + identifier).json()
        assert saved["status"] == "outcome_unknown" and len(saved["messages"]) == 1
        assert resumed.post(CHAT, json=payload()).json()["id"] == identifier
    assert len(runtime.requests) <= 1
    with db.session() as session:
        assert session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one().reserved_tokens > 0
