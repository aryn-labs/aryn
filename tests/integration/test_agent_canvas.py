import copy
import time

import pytest

from database.repositories.organization_repo import OrganizationRepository
from database.schema import AgentVersionModel, RunStateModel
from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT
from tests.integration.test_agent_editor import definition
from tests.integration.test_studio_api import PREFIX, draft, studio as studio


def graph():
    return {"schema_version": "1.0.0", "nodes": [
        {"id": kind, "type": kind, "x": index * 300, "y": 100}
        for index, kind in enumerate(("input", "agent", "output"))], "connections": [
            {"source": "input", "source_port": "text", "target": "agent", "target_port": "input"},
            {"source": "agent", "source_port": "result", "target": "output", "target_port": "result"}]}


def setup(client):
    bp, version = draft(client)
    base = PREFIX + f"/blueprints/{bp['id']}"
    value = definition(version)
    assert client.post(base + "/working-copy", json={"expected_generation": 0, "definition": value}).status_code == 200
    assert client.post(base + "/editor-layout", json={"expected_generation": 0, "graph": graph()}).status_code == 200
    return base, bp, version


def preview_body(**overrides):
    return {"expected_generation": 1, "expected_layout_generation": 1, "prompt": "Jelaskan likuiditas secara singkat.",
        "idempotency_key": "canvas-preview-test-key", "allow_remote_model": True, **overrides}


def wait(client, path):
    for _ in range(100):
        data = client.get(path).json()
        if data["result"]["status"] in {"completed", "failed", "cancelled", "outcome_unknown"}:
            return data
        time.sleep(0.01)
    pytest.fail("Core preview did not reach a terminal state")


def test_preview_actual_core_events_usage_persistence_and_idempotency(studio):
    client, db, runtime, app = studio
    base, bp, version = setup(client)
    capabilities = client.get(PREFIX + "/factory/capabilities").json()
    assert capabilities["tools"] == [] and capabilities["draft_defaults"]["tool_grants"] == []
    response = client.post(base + "/preview-runs", json=preview_body())
    assert response.status_code == 202, response.text
    run_id = response.json()["result"]["run_id"]
    result = wait(client, base + "/preview-runs/" + run_id)
    assert [event["type"] for event in result["events"]] == ["input.accepted", "agent.dispatched", "run.completed"]
    assert result["telemetry"] == "core_lifecycle_only" and not result["cancellation_supported"]
    assert result["result"]["execution_claim_verified"] and result["result"]["usage"]["total_tokens"] == 50
    assert result["result"]["actual_model"] == version["model"]
    assert result["result"]["agent_version_id"] is None and result["result"]["assignment_id"] is None
    assert client.post(base + "/preview-runs", json=preview_body()).status_code == 202
    assert len(runtime.requests) == 1
    with db.session() as session:
        assert session.query(AgentVersionModel).count() == 1
        assert session.query(RunStateModel).filter_by(execution_mode="agent_preview").count() == 1
        assert session.get(AgentVersionModel, version["id"]).payload_hash == version["payload_hash"]
    # A fresh service instance reads authenticated stored events without inference.
    from modules.core.agent_preview import AgentPreviewService
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    restored = AgentPreviewService(app.state.agent_preview.core, app.state.agent_preview.editor).read(ctx, bp["id"], run_id)
    assert restored.result.output == result["result"]["output"] and len(runtime.requests) == 1


@pytest.mark.parametrize("mutation", ["wrong_port", "duplicate", "cycle", "foreign", "tool", "forged", "nan"])
def test_canvas_rejects_invalid_topology_and_tool_authority(studio, mutation):
    client, _, _, _ = studio
    base, _, _ = setup(client)
    value = graph()
    if mutation == "wrong_port":
        value["connections"][0]["source_port"] = "policy"
    if mutation == "duplicate":
        value["connections"].append(copy.deepcopy(value["connections"][0]))
    if mutation == "cycle":
        value["connections"][0]["target"] = "input"
    if mutation == "foreign":
        value["nodes"].pop(0)
    if mutation == "tool":
        value["nodes"][0]["type"] = "browser"
    if mutation == "forged":
        value["tool_grants"] = ["browser"]
    if mutation == "nan":
        value["nodes"][0]["x"] = "NaN"
    assert client.post(base + "/editor-layout", json={"expected_generation": 1, "graph": value}).status_code == 422


def test_preview_generation_consent_permission_model_and_project_boundaries(studio):
    client, db, runtime, _ = studio
    base, _, _ = setup(client)
    for overrides, code in [({"expected_generation": 2}, 409), ({"expected_layout_generation": 2}, 409),
            ({"allow_remote_model": False}, 422), ({"tool_grants": ["browser"]}, 422)]:
        assert client.post(base + "/preview-runs", json=preview_body(**overrides)).status_code == code
    response = client.post(base + "/preview-runs", json=preview_body())
    run_id = response.json()["result"]["run_id"]
    wait(client, base + "/preview-runs/" + run_id)
    assert client.get(base.replace("/projects/", "/projects/foreign-") + "/preview-runs/" + run_id).status_code in {403, 404}
    other, _ = draft(client, "other-preview-agent")
    assert client.get(PREFIX + f"/blueprints/{other['id']}/preview-runs/{run_id}").status_code == 404
    with db.session(write=True) as session:
        OrganizationRepository(session).get_member(DEV_ORG, DEV_ACTOR).role = "viewer"
        OrganizationRepository(session).add_project_member(DEV_PROJECT, DEV_ACTOR, "viewer")
    assert client.get(base + "/preview-runs/" + run_id).status_code == 200
    assert client.post(base + "/preview-runs", json=preview_body(idempotency_key="denied-preview-test-key")).status_code == 403
    assert len(runtime.requests) == 1


@pytest.mark.parametrize("status", ["failed", "outcome_unknown", "cancelled"])
def test_preview_terminal_outcomes_are_not_success(studio, status):
    from packages.contracts.runtime import RunStatus
    client, _, runtime, _ = studio
    base, _, _ = setup(client)
    runtime.status = RunStatus(status)
    started = client.post(base + "/preview-runs", json=preview_body()).json()
    result = wait(client, base + "/preview-runs/" + started["result"]["run_id"])
    assert result["result"]["status"] == status and not result["result"]["output"]
    assert result["events"][-1]["type"] == "run." + status


def test_incomplete_graph_is_saved_but_cannot_run_and_layout_conflicts(studio):
    client, _, runtime, _ = studio
    base, _, _ = setup(client)
    value = graph()
    value["connections"] = []
    assert client.post(base + "/editor-layout", json={"expected_generation": 1, "graph": value}).status_code == 200
    assert client.post(base + "/editor-layout", json={"expected_generation": 1, "graph": graph()}).status_code == 409
    assert client.post(base + "/preview-runs", json=preview_body(expected_layout_generation=2)).status_code == 409
    assert not runtime.requests


@pytest.mark.parametrize("availability", ["unavailable", "unknown"])
def test_preview_model_preflight_has_no_false_dispatch_or_output(studio, availability):
    from packages.contracts.runtime import RuntimeModelAvailability
    client, _, runtime, _ = studio
    base, _, _ = setup(client)
    async def unavailable(model, **kwargs):
        return RuntimeModelAvailability(model=model, status=availability, source="isolated-test", reason="provider_rejected")
    runtime.model_availability = unavailable
    response = client.post(base + "/preview-runs", json=preview_body())
    assert response.status_code == 202
    result = wait(client, base + "/preview-runs/" + response.json()["result"]["run_id"])
    assert result["result"]["status"] in {"failed", "outcome_unknown"}
    assert not result["result"]["output"] and not runtime.requests
    assert "agent.dispatched" not in [event["type"] for event in result["events"]]


def test_preview_cannot_enable_runtime_tools_and_budget_is_authoritative(studio):
    from database.schema import UsageBudgetModel
    client, db, runtime, _ = studio
    base, _, _ = setup(client)
    runtime.tools = ["browser"]
    assert client.post(base + "/preview-runs", json=preview_body()).status_code == 503
    assert not runtime.requests
    runtime.tools = []
    with db.session(write=True) as session:
        session.query(UsageBudgetModel).filter_by(project_id=DEV_PROJECT).update({"max_tokens_per_run": 1})
    assert client.post(base + "/preview-runs", json=preview_body()).status_code == 403
    assert not runtime.requests


def test_preview_actual_timeout_is_unknown_and_retry_cannot_redispatch(studio, monkeypatch):
    import asyncio
    from tests.security.test_core_execution_authority import freeze_admission_clock
    client, _, runtime, _ = studio
    base, _, _ = setup(client)
    resume = freeze_admission_clock(monkeypatch)
    entered = []
    async def stalled(request, context):
        entered.append(request)
        resume()
        await asyncio.sleep(10)
    runtime.execute_direct_turn = stalled
    runtime.timeout = 0.05
    response = client.post(base + "/preview-runs", json=preview_body())
    path = base + "/preview-runs/" + response.json()["result"]["run_id"]
    result = wait(client, path)
    assert result["result"]["status"] == "outcome_unknown"
    assert result["result"]["usage"]["availability"] == "unavailable"
    assert result["events"][-1]["type"] == "run.outcome_unknown"
    assert client.post(base + "/preview-runs", json=preview_body()).json()["result"]["run_id"] == result["result"]["run_id"]
    assert len(entered) == 1


def test_preview_origin_csrf_and_authenticated_reference_cannot_be_forged(studio, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from database.repositories.audit_repo import AuditRepository
    from database.schema import AuditEventModel
    client, db, runtime, _ = studio
    base, _, _ = setup(client)
    assert client.post(base + "/preview-runs", json=preview_body(), headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post(base + "/preview-runs", json=preview_body(), headers={"Origin": "https://evil.example"}).status_code == 403
    response = client.post(base + "/preview-runs", json=preview_body()).json()
    path = base + "/preview-runs/" + response["result"]["run_id"]
    result = wait(client, path)
    assert result["result"]["raw_response"] == {} and result["result"]["execution_evidence"] is None
    with pytest.raises(IntegrityError, match="append-only"):
        with db.session(write=True) as session:
            row = session.query(AuditEventModel).filter_by(resource_id=result["result"]["run_id"], event_type="factory.preview.accepted").one()
            session.execute(text("UPDATE audit_events SET redacted_payload_json='{}' WHERE id=:id"), {"id": row.id})
    original_verify = AuditRepository.verify_authenticated_event
    monkeypatch.setattr(AuditRepository, "verify_authenticated_event",
        lambda self, row: row.event_type != "factory.preview.accepted" and original_verify(self, row))
    assert client.get(path).status_code == 404
    assert len(runtime.requests) == 1
