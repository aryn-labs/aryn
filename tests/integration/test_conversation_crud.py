"""Conversation CRUD never modifies signed messages or execution governance."""
import asyncio
import time
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.schema import ConversationChangeModel, MembershipModel, RunStateModel, UsageBudgetModel
from packages.contracts.chat import ConversationRenameInput, ConversationDeleteInput
from tests.integration.test_conversations import chat_studio, raw_studio, CHAT, payload, complete
from tests.integration.test_studio_api import DEV_ACTOR, DEV_ORG, DEV_PROJECT

__all__ = ["chat_studio", "raw_studio"]


def intent(revision=0, request_id="conversation-mutation-001", **extra):
    return dict(expected_metadata_revision=revision, idempotency_key=request_id, **extra)


def start(studio):
    client, _, _, _ = studio
    response = client.post(CHAT, json=payload())
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    return identifier, complete(client, identifier)


def test_rename_read_refresh_multiturn_and_duplicates(chat_studio):
    client, db, runtime, app = chat_studio
    identifier, original = start(chat_studio)
    body = intent(title="  Renamed research conversation  ")
    first = client.patch(CHAT + "/" + identifier, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["title"] == "Renamed research conversation"
    assert first.json()["metadata_revision"] == 1
    assert client.patch(CHAT + "/" + identifier, json=body).json() == first.json()
    assert client.patch(CHAT + "/" + identifier, json={**body, "title": "Different"}).status_code == 409
    assert client.patch(CHAT + "/" + identifier, json=intent(request_id="conversation-stale-002", title="Stale")).status_code == 409
    loaded = client.get(CHAT + "/" + identifier).json()
    assert loaded["messages"] == original["messages"] and loaded["revision"] == original["revision"]
    assert loaded["title"] == client.get(CHAT).json()["items"][0]["title"] == first.json()["title"]
    from modules.core.conversations import Conversations
    service = Conversations(app.state.coordinator, app.state.conversations.catalog, app.state.conversations.require_runtime)
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    assert service.read(ctx, identifier)["title"] == first.json()["title"]
    follow = {**payload(), "idempotency_key": "test-crud-request-0002", "expected_revision": 1}
    assert client.post(CHAT + "/" + identifier + "/messages", json=follow).status_code == 202
    assert complete(client, identifier)["metadata_revision"] == 1
    assert len(runtime.requests) == 2
    with db.session() as session:
        assert session.query(ConversationChangeModel).count() == 1
        assert session.execute(text("SELECT COUNT(*) FROM audit_events WHERE event_type='chat.conversation.renamed'")).scalar() == 1


def test_delete_retains_governance_and_permanently_denies_old_id(chat_studio):
    client, db, runtime, app = chat_studio
    identifier, _ = start(chat_studio)
    with db.session() as session:
        snapshots = {table: session.execute(text(f"SELECT * FROM {table}")).all() for table in (
            "chat_conversations", "chat_turns", "run_states", "usage_budgets", "audit_events")}
    body = intent()
    first = client.request("DELETE", CHAT + "/" + identifier, json=body)
    assert first.status_code == 200 and first.json()["deleted"], first.text
    assert client.request("DELETE", CHAT + "/" + identifier, json=body).json() == first.json()
    assert client.request("DELETE", CHAT + "/" + identifier, json=intent(request_id="conversation-second-delete")).json() == first.json()
    assert client.request("DELETE", CHAT + "/" + identifier, json=intent(request_id=body["idempotency_key"], revision=1)).status_code == 409
    assert client.get(CHAT).json()["items"] == []
    assert client.get(CHAT + "/" + identifier).status_code == 404
    assert client.patch(CHAT + "/" + identifier, json=intent(revision=1, request_id="conversation-rename-deleted", title="Resurrect")).status_code == 404
    assert client.post(CHAT, json=payload()).status_code == 404  # old creation key cannot resurrect it
    follow = {**payload(), "idempotency_key": "conversation-deleted-followup", "expected_revision": 1}
    assert client.post(CHAT + "/" + identifier + "/messages", json=follow).status_code == 404
    from modules.core.conversations import ChatError, Conversations
    service = Conversations(app.state.coordinator, app.state.conversations.catalog, app.state.conversations.require_runtime)
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    with pytest.raises(ChatError) as error:
        service.read(ctx, identifier)
    assert error.value.status == 404
    with db.session() as session:
        for table, before in snapshots.items():
            if table != "audit_events":
                assert session.execute(text(f"SELECT * FROM {table}")).all() == before
        after = session.execute(text("SELECT * FROM audit_events")).all()
        assert all(row in after for row in snapshots["audit_events"]) and len(after) == len(snapshots["audit_events"]) + 1
        assert session.query(ConversationChangeModel).count() == 1
    assert len(runtime.requests) == 1


@pytest.mark.parametrize("extra", [{"title": " "}, {"title": "x" * 121}, {"title": "Two\nlines"}, {"title": "Hidden\u202etext"},
    {"title": 12}, {"actor_id": "forged"}, {"message": "rewrite"}, {"expected_metadata_revision": True}, {"expected_metadata_revision": -1}, {"idempotency_key": "short"}])
def test_patch_strict_validation_does_not_mutate(chat_studio, extra):
    client, db, _, _ = chat_studio
    identifier, _ = start(chat_studio)
    assert client.patch(CHAT + "/" + identifier, json={**intent(title="Valid"), **extra}).status_code == 422
    with db.session() as session:
        assert session.query(ConversationChangeModel).count() == 0


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_csrf_origin_permissions_and_ownership(chat_studio, method):
    client, db, _, app = chat_studio
    identifier, _ = start(chat_studio)
    body = intent(**({"title": "New title"} if method == "PATCH" else {}))
    assert client.request(method, CHAT + "/" + identifier, json=body, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert client.request(method, CHAT + "/" + identifier, json=body, headers={"Origin": "https://foreign.example"}).status_code == 403
    from database.repositories.organization_repo import OrganizationRepository
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.add_member(DEV_ORG, "other-user", role="admin")
        repo.create_project(app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "other-project"), "other-project", "Other", "other")
        repo.create_organization("other-org", "Other", "other-org")
        repo.add_member("other-org", DEV_ACTOR, role="admin")
        repo.create_project(app.state.binder.create_trusted_context(DEV_ACTOR, "other-org", "foreign-project"), "foreign-project", "Foreign", "foreign")
    assert client.request(method, "/api/projects/other-project/chat/conversations/" + identifier, json=body).status_code == 404
    from modules.core.conversations import ChatError
    model = ConversationRenameInput(**body) if method == "PATCH" else ConversationDeleteInput(**body)
    for actor, org, project in [("other-user", DEV_ORG, DEV_PROJECT), (DEV_ACTOR, DEV_ORG, "other-project"), (DEV_ACTOR, "other-org", "foreign-project")]:
        with pytest.raises(ChatError) as error:
            app.state.conversations.metadata.mutate(app.state.binder.create_trusted_context(actor, org, project), identifier, model, delete=method == "DELETE")
        assert error.value.status == 404
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(user_id=DEV_ACTOR, organization_id=DEV_ORG).update({"role": "viewer"})
    assert client.request(method, CHAT + "/" + identifier, json=body).status_code == 403
    with db.session() as session:
        assert session.query(ConversationChangeModel).count() == 0


def test_inflight_delete_settles_usage_without_resurrection(chat_studio):
    client, db, runtime, _ = chat_studio
    original = runtime.execute_direct_turn
    release = threading.Event()
    async def delayed(request, context):
        while not release.is_set():
            await asyncio.sleep(0.01)
        return await original(request, context)
    runtime.execute_direct_turn = delayed
    first = client.post(CHAT, json=payload())
    identifier = first.json()["id"]
    assert first.json()["status"] == "processing"
    assert client.patch(CHAT + "/" + identifier, json=intent(title="Name while processing")).status_code == 200
    assert client.request("DELETE", CHAT + "/" + identifier, json=intent(revision=1, request_id="inflight-delete-request")).status_code == 200
    assert client.get(CHAT + "/" + identifier).status_code == 404
    release.set()
    for _ in range(120):
        with db.session() as session:
            run = session.query(RunStateModel).filter_by(project_id=DEV_PROJECT).one()
            if run.status == "completed":
                assert run.usage_settled == 1 and run.execution_attestation
                budget = session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one()
                assert budget.reserved_tokens == 0 and budget.cumulative_tokens == 50
                break
        time.sleep(0.01)
    else:
        pytest.fail("Admitted run did not settle")
    assert len(runtime.requests) == 1
    assert client.get(CHAT).json()["items"] == []
    assert client.post(CHAT + "/" + identifier + "/messages", json={**payload(), "expected_revision": 1, "idempotency_key": "post-delete-inflight-followup"}).status_code == 404


def test_metadata_db_guards_and_rollback_cannot_resurrect(chat_studio):
    client, db, _, _ = chat_studio
    identifier, _ = start(chat_studio)
    assert client.patch(CHAT + "/" + identifier, json=intent(title="Signed name")).status_code == 200
    assert client.request("DELETE", CHAT + "/" + identifier, json=intent(revision=1, request_id="conversation-delete-002")).status_code == 200
    for statement in ("UPDATE chat_conversation_changes SET title='forged'", "DELETE FROM chat_conversation_changes",
        "INSERT OR REPLACE INTO chat_conversation_changes SELECT * FROM chat_conversation_changes"):
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(statement))
    from database.chat_protection import install_chat_protection
    with db.engine.begin() as connection:
        for action in ("insert", "update", "delete"):
            connection.execute(text(f"DROP TRIGGER aryn_chat_conversation_changes_{action}"))
        connection.execute(text("DELETE FROM chat_conversation_changes WHERE generation=2"))
        install_chat_protection(connection)
    assert client.get(CHAT + "/" + identifier).status_code == 503
    assert client.get(CHAT).status_code == 503
    assert client.post(CHAT + "/" + identifier + "/messages", json={**payload(), "expected_revision": 1, "idempotency_key": "rollback-denied-followup"}).status_code == 503


def test_metadata_populated_downgrade_refused(chat_studio):
    client, db, _, _ = chat_studio
    # Metadata-created fixture has no Alembic head; stamp it solely in this disposable test.
    from alembic import command
    from alembic.config import Config
    identifier, _ = start(chat_studio)
    client.request("DELETE", CHAT + "/" + identifier, json=intent())
    with db.engine.begin() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.stamp(config, "head")
        with pytest.raises(RuntimeError, match="tombstones"):
            command.downgrade(config, "022_chat_preferences")


def test_upgrade_existing_conversation_does_not_rewrite_evidence(chat_studio):
    from alembic import command
    from alembic.config import Config
    client, db, _, _ = chat_studio
    identifier, before = start(chat_studio)
    with db.engine.begin() as connection:
        # Represent a populated 022 store: metadata was never changed.
        assert connection.execute(text("SELECT COUNT(*) FROM chat_conversation_changes")).scalar() == 0
        connection.execute(text("DROP TABLE chat_conversation_changes"))
        # Metadata-built fixtures also contain later Project columns/receipts.
        # Remove those empty additions to faithfully represent a 022 database.
        assert connection.execute(text("SELECT COUNT(*) FROM project_mutations")).scalar() == 0
        connection.execute(text("DROP TABLE project_mutations"))
        connection.execute(text("ALTER TABLE projects DROP COLUMN description"))
        connection.execute(text("ALTER TABLE projects DROP COLUMN generation"))
        for table in ("incident_capsule_replays", "incident_capsules", "brief_interpretations",
                "evidence_references", "evidence_connections", "bench_scenario_candidates", "bench_suite_versions"):
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0
            connection.execute(text(f"DROP TABLE {table}"))
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.stamp(config, "022_chat_preferences")
        evidence = {table: connection.execute(text(f"SELECT * FROM {table}")).all() for table in (
            "chat_conversations", "chat_turns", "run_states", "usage_budgets", "audit_events", "chat_provider_consents")}
        command.upgrade(config, "head")
        for table, rows in evidence.items():
            assert connection.execute(text(f"SELECT * FROM {table}")).all() == rows
    assert client.get(CHAT + "/" + identifier).json() == before
    assert client.patch(CHAT + "/" + identifier, json=intent(title="Migrated title")).status_code == 200


def test_unknown_run_retains_reservation_after_delete(chat_studio):
    client, db, runtime, _ = chat_studio
    async def unknown(request, context):
        runtime.requests.append(request)
        raise TimeoutError("not exposed")
    runtime.execute_direct_turn = unknown
    identifier, result = start(chat_studio)
    assert result["status"] == "outcome_unknown"
    with db.session() as session:
        reserved = session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one().reserved_tokens
    assert reserved > 0
    assert client.request("DELETE", CHAT + "/" + identifier, json=intent()).status_code == 200
    with db.session() as session:
        assert session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one().reserved_tokens == reserved
        assert session.query(RunStateModel).one().status == "outcome_unknown"


def test_concurrent_duplicate_rename_has_one_receipt(chat_studio):
    from concurrent.futures import ThreadPoolExecutor
    client, db, _, _ = chat_studio
    identifier, _ = start(chat_studio)
    body = intent(title="One accepted title")
    def rename():
        return client.patch(CHAT + "/" + identifier, json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rename(), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert results[0].json() == results[1].json()
    with db.session() as session:
        assert session.query(ConversationChangeModel).count() == 1
