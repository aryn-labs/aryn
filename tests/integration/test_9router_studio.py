import pytest
import json
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_studio_api import studio, draft, promoted, PREFIX, ORIGIN
from packages.model_adapters.gateway import GatewaySettings
from services.api.studio import create_app
from packages.contracts.runtime import GatewayDiscovery, RuntimeModelAvailability
from packages.runtime_adapters import RuntimeAuthenticationError


@pytest.mark.parametrize("configured", [False, True])
def test_runtime_auth_failure_distinguishes_healthy_process_from_readiness(studio, configured):
    client, db, runtime, app = studio
    runtime.api_key = "isolated-runtime-key" if configured else ""
    async def rejected():
        raise RuntimeAuthenticationError("Authentication refused")
    runtime.capabilities = rejected
    state = client.get("/api/workspace").json()["runtime"]
    assert state["connected"] is True and state["ready"] is False
    assert state["reason"] == ("runtime_authentication_rejected" if configured else "runtime_authentication_missing")
    assert "Autentikasi ARYN Runtime" in state["message"]
    assert "isolated-runtime-key" not in json.dumps(state)
    bp, version = draft(client)
    response = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert response.status_code == 503 and runtime.requests == []


@pytest.mark.parametrize("status", ["unavailable", "unknown"])
def test_model_gate_blocks_bench_and_run_preserving_historical_evidence(studio, status):
    client, db, runtime, app = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    calls_before = len(runtime.requests)
    async def unavailable(model, **kwargs):
        return RuntimeModelAvailability(model=model, status=status)
    runtime.model_availability = unavailable
    bench = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert bench.status_code in {409, 503}
    run = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "Isolated test",
                      "idempotency_key": "gateway-blocked-model", "allow_remote_model": True})
    assert run.status_code in {409, 503}
    assert len(runtime.requests) == calls_before
    with db.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM bench_evaluations")).scalar() == 1
        assert session.execute(text("SELECT COUNT(*) FROM run_states WHERE execution_mode != 'bench'")).scalar() == 0
        assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []


def test_discovery_failure_cannot_keep_stale_catalog_or_create_version(studio):
    client, db, runtime, app = studio
    bp, _ = draft(client)
    async def offline(**kwargs):
        return GatewayDiscovery()
    runtime.discover_models = offline
    workspace = client.get("/api/workspace").json()
    assert workspace["models"] == [] and workspace["gateway"]["connected"] is False
    response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json={"version_number": "2.0.0",
                           "system_prompt": "Follow all existing research safety guidelines.", "model": "test/model-a"})
    assert response.status_code == 503
    assert runtime.requests == []


def test_exact_model_provenance_persists_and_cached_result_works_offline(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    payload = {"assignment_id": assignment["id"], "prompt": "Isolated exact model execution",
               "idempotency_key": "exact-gateway-cached-result", "allow_remote_model": True}
    response = client.post(PREFIX + "/runs", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["requested_model"] == result["actual_model"] == version["model"]
    assert result["gateway"] == "9Router" and result["runtime_backend"] == "Hermes"
    async def offline(**kwargs):
        return GatewayDiscovery()
    runtime.discover_models = offline
    assert client.get("/api/workspace").json()["models"] == []
    repeat = client.post(PREFIX + "/runs", json=payload)
    assert repeat.status_code == 200 and repeat.json()["actual_model"] == version["model"]
    assert len(runtime.requests) == 5
    with db.session() as session:
        assert session.execute(text("SELECT actual_model, gateway, runtime_backend FROM run_states WHERE execution_mode != 'bench'")).one() == (version["model"], "9Router", "Hermes")
        assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"


@pytest.mark.parametrize("change", ["different_model", "missing_evidence"])
def test_core_rejects_model_substitution_or_missing_gateway_evidence(studio, change):
    client, db, runtime, app = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    execute = runtime.execute_direct_turn
    async def tampered(request, context):
        result = await execute(request, context)
        if change == "different_model":
            result.model = result.actual_model = "test/model-substitute"
        else:
            result.gateway = result.actual_model = result.requested_model = None
        return result
    runtime.execute_direct_turn = tampered
    response = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"],
                           "prompt": "Isolated rejection test", "idempotency_key": "exact-model-rejected-turn",
                           "allow_remote_model": True})
    assert response.status_code == 409, response.text
    assert "Eksekusi ditolak" in response.json()["message"]
    assert len(runtime.requests) == 5  # four Bench + one runtime call; no fallback
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert snapshot["runs"][0]["status"] == "failed"
    assert snapshot["runs"][0]["actual_model"] is None


def test_gateway_credentials_cannot_enter_responses_audit_database_or_logs(studio, caplog):
    _, db, runtime, _ = studio
    secret = "isolated-gateway-key-never-persist"
    runtime.api_key = "isolated-runtime-key-never-persist"
    runtime.model_gateway = SimpleNamespace(settings=GatewaySettings(api_key=secret))
    app = create_app(db, runtime, testing=True)
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
        session = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrf"]})
        bp, version = draft(client)
        assignment = promoted(client, bp, version)
        # Even escaped JSON and approval comments cannot copy a server secret into storage.
        for credential in (secret, runtime.api_key):
            response = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json={
                "version_number": "2.0.0", "system_prompt": "Instruction containing " + credential,
                "model": version["model"]})
            assert response.status_code == 422 and credential not in response.text
        response = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"],
            "prompt": "Isolated secret boundary test", "idempotency_key": "isolated-gateway-secret-run",
            "allow_remote_model": True, "api_key": "browser-provider-key"})
        assert response.status_code == 422
        payload = json.dumps({"assignment_id": assignment["id"], "prompt": "Input " + secret,
            "idempotency_key": "isolated-gateway-secret-run", "allow_remote_model": True})
        payload = payload.replace(secret, "".join("\\u%04x" % ord(c) for c in secret))
        assert client.post(PREFIX + "/runs", content=payload, headers={"Content-Type": "application/json"}).status_code == 422
        workspace = client.get("/api/workspace")
        snapshot = client.get(PREFIX + "/snapshot")
        assert secret not in workspace.text + snapshot.text + caplog.text
        assert runtime.api_key not in workspace.text + snapshot.text + caplog.text
        assert "connect-src 'self'" in workspace.headers["Content-Security-Policy"]
    with db.session() as session:
        for name in ("agent_versions", "bench_evaluations", "audit_events", "run_states"):
            rows = session.execute(text(f"SELECT * FROM {name}")).all()
            assert secret not in repr(rows) and runtime.api_key not in repr(rows)
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []
