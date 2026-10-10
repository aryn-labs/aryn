"""A real Core/API with HTTP doubles: public catalog listing is never readiness evidence."""
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from database.connection import DatabaseManager, create_db_engine, init_db
from database.schema import ConversationTurnModel, RunStateModel, UsageBudgetModel
from packages.contracts.runtime import RuntimeHealth, RuntimeCapabilities, RunRequest, ModelUnavailableError
from services.api.studio import create_app, DEV_PROJECT, DEV_ORG, DEV_ACTOR
from tests.gateway_fixtures import MODEL, COMPLETION, make_adapter, standard_handler

PREFIX = f"/api/projects/{DEV_PROJECT}/chat"
ORIGIN = "http://127.0.0.1:8710"


@pytest.fixture
def verified_studio(tmp_path):
    db = DatabaseManager(create_db_engine(f"sqlite:///{tmp_path / 'probe.sqlite3'}"))
    init_db(db.engine)
    calls, state = [], {"failure": None, "listed": True}

    def handler(request):
        if request.url.port == 20128:
            return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}] if state["listed"] else []})
        if request.method == "POST":
            calls.append(request)
            if state["failure"]:
                return httpx.Response(409, json={"error": {"code": state["failure"]}})
            return httpx.Response(200, json={**COMPLETION, "id": f"test-probe-{len(calls)}"})
        return standard_handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = make_adapter(http)

    async def health():
        return RuntimeHealth(is_healthy=True, status="ok", platform="isolated-http-test",
            version="test-only", listener_url="isolated")

    async def capabilities():
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True)

    runtime.health, runtime.capabilities = health, capabilities
    app = create_app(db, runtime, testing=True)
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50000)) as client:
        session = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrf"]})
        policy = client.get(PREFIX + "/provider-consent").json()["models"][MODEL]
        assert client.post(PREFIX + "/provider-consent", json={"model": MODEL, "policy": policy["policy"]}).status_code == 200
        yield client, db, runtime, app, calls, state
    import asyncio
    asyncio.run(http.aclose())
    db.engine.dispose()


def payload():
    return dict(message="A real question in an isolated test", model=MODEL,
        idempotency_key="chat-verification-request-001", allow_remote_model=True)


def finish(client, identifier):
    for _ in range(100):
        response = client.get(PREFIX + "/conversations/" + identifier).json()
        if response["status"] != "processing":
            return response
        time.sleep(0.01)
    pytest.fail("Test turn did not complete")


def test_unknown_candidate_is_probed_and_settled_before_chat_dispatch(verified_studio):
    client, db, _, _, calls, _ = verified_studio
    capability = client.get(PREFIX + "/capability").json()
    assert capability["can_send"]
    assert capability["models"][0] == dict(id=MODEL, name=MODEL, available=False, verifiable=True)
    assert not calls  # Viewing Home never dispatches inference.
    response = client.post(PREFIX + "/conversations", json=payload())
    assert response.status_code == 202, response.text
    result = finish(client, response.json()["id"])
    assert result["status"] == "completed" and len(calls) == 2
    import json
    assert json.loads(calls[0].content)["messages"][-1]["content"] == "Reply with the word Ready."
    assert payload()["message"] not in str(calls[0].content)
    with db.session() as session:
        rows = session.query(RunStateModel).order_by(RunStateModel.created_at).all()
        assert [row.execution_mode for row in rows] == ["model_probe", "direct"]
        assert all(row.status == "completed" and row.execution_attestation for row in rows)
        assert session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one().cumulative_tokens == 10
    repeated = client.post(PREFIX + "/conversations", json=payload())
    assert repeated.json()["id"] == result["id"] and len(calls) == 2
    assert client.get(PREFIX + "/capability").json()["models"][0]["available"]
    follow = {**payload(), "message": "Follow up", "expected_revision": 1,
        "idempotency_key": "chat-verification-request-002"}
    response = client.post(PREFIX + "/conversations/" + result["id"] + "/messages", json=follow)
    assert response.status_code == 202
    assert finish(client, result["id"])["revision"] == 2 and len(calls) == 3


@pytest.mark.parametrize("changes,status", [
    ({"model": "unlisted/model"}, 503),
    ({"expected_revision": 1}, 409), ({"availability_verified": True}, 422),
])
def test_candidate_never_bypasses_consent_scope_or_client_authority(verified_studio, changes, status):
    client, _, _, _, calls, _ = verified_studio
    assert client.post(PREFIX + "/conversations", json={**payload(), **changes}).status_code == status
    assert not calls
    assert client.post("/api/projects/foreign/chat/conversations", json=payload()).status_code == 403
    assert not calls


@pytest.mark.parametrize("failure", ["actual_model_mismatch", "gateway_rejected", "invalid_gateway_completion"])
def test_failed_probe_never_accepts_message_or_repeats_uncertain_inference(verified_studio, failure):
    client, db, _, _, calls, state = verified_studio
    state["failure"] = failure
    first = client.post(PREFIX + "/conversations", json=payload())
    assert first.status_code == 503 and first.json()["error_code"] == (
        "model_identity_invalid" if failure == "actual_model_mismatch" else "model_verification_unresolved")
    assert client.post(PREFIX + "/conversations", json=payload()).status_code == 503
    assert len(calls) == 1
    with db.session() as session:
        assert session.query(ConversationTurnModel).count() == 0
        assert session.query(RunStateModel).count() == 1
        assert session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).one().reserved_tokens > 0


def test_probe_has_no_client_prompt_escape_and_normal_runs_stay_fail_closed(verified_studio):
    client, _, runtime, app, calls, _ = verified_studio
    client.get(PREFIX + "/capability")
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    import asyncio
    with pytest.raises(ModelUnavailableError):
        asyncio.run(app.state.coordinator.execute_managed_direct_turn(RunRequest(prompt="user prompt", model=MODEL), ctx))
    from modules.core.permissions.engine import PermissionDeniedError
    with pytest.raises(PermissionDeniedError):
        asyncio.run(app.state.coordinator.execute_managed_direct_turn(RunRequest(prompt="forged probe", model=MODEL), ctx,
            _execution_mode="model_probe", _model_verification=True))
    assert not calls
    assert asyncio.run(runtime.model_availability(MODEL)).status == "unknown"


def test_probe_respects_budget_and_csrf(verified_studio):
    client, db, _, _, calls, _ = verified_studio
    assert client.post(PREFIX + "/conversations", json=payload(), headers={"X-CSRF-Token": "invalid"}).status_code == 403
    with db.session(write=True) as session:
        session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).update({"max_tokens_per_run": 20})
    assert client.post(PREFIX + "/conversations", json=payload()).status_code == 403
    assert not calls
