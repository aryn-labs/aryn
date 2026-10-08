"""Studio sends acceptance intent; the server resolves every governance decision."""
from tests.integration.test_studio_api import studio as studio
from tests.integration.test_studio_api import draft, PREFIX
from tests.bench_fixtures import generic_suite, install_generic_suite
from packages.contracts.bench import RegressionPolicy


def test_baseline_api_and_server_regression_gate_cannot_be_overridden(studio, monkeypatch):
    client, db, runtime, app = studio
    install_generic_suite(monkeypatch, generic_suite(min_score_threshold=0.5, required_scenarios=["summary"],
        regression_policy=RegressionPolicy(critical_scenarios=["extraction"])))
    original = runtime.execute_direct_turn
    failing = False
    async def structured(request, context):
        result = await original(request, context)
        result.output = "{}" if failing and request.metadata["scenario_id"] == "extraction" else '{"summary":"Grounded JSON"}'
        return result
    runtime.execute_direct_turn = structured
    bp = client.post(PREFIX + "/blueprints", json={"name": "Generic regression", "slug": "generic-regression"}).json()
    def version(number):
        result = client.post(PREFIX + f"/blueprints/{bp['id']}/versions", json={"version_number": number,
            "system_prompt": "Produce grounded structured JSON evidence.", "model": "test/model-a",
            "evaluation_reference": {"suite_id": "analysis", "min_score_threshold": 0.5, "required_scenarios": ["summary"]},
            "output_contract": {"format": "json", "schema_definition": {"type": "object"}}})
        assert result.status_code == 201, result.text
        return result.json()
    prior = version("1.0.0")
    evaluation = client.post(PREFIX + f"/versions/{prior['id']}/bench", json={"allow_remote_model": True}).json()
    baseline = client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json={"evaluation_id": evaluation["evaluation_id"],
        "reason": "Reviewed generic verified baseline."})
    assert baseline.status_code == 200, baseline.text
    baseline = baseline.json()
    assert baseline["suite_id"] == "structured-analysis"
    current = version("2.0.0")
    failing = True
    evaluation = client.post(PREFIX + f"/versions/{current['id']}/bench", json={"allow_remote_model": True})
    assert evaluation.status_code == 200 and evaluation.json()["passed"]
    assert evaluation.json()["evaluation"]["regression"]["promotion_blocked"]
    response = client.post(PREFIX + f"/versions/{current['id']}/approve", json={"payload_hash": current["payload_hash"], "comments": "Review"})
    assert response.status_code == 409 and response.json()["comparison"]["reason"] == "critical_regression"
    assert client.post(PREFIX + f"/versions/{current['id']}/publish", json={"critical": False, "regression_passed": True}).status_code == 409
    assert client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json={"evaluation_id": evaluation.json()["evaluation_id"],
        "expected_baseline_id": baseline["baseline_id"], "reason": "Cannot waive regression.", "baseline": True}).status_code == 422
    assert client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json={"evaluation_id": evaluation.json()["evaluation_id"],
        "expected_baseline_id": baseline["baseline_id"], "reason": "Cannot pretend same-suite failure is evolution.", "suite_transition": True}).status_code == 409
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert snapshot["accepted_baselines"][0]["baseline_id"] == baseline["baseline_id"]
    candidate = next(v for v in snapshot["versions"] if v["id"] == current["id"])
    assert candidate["integrity_valid"] and not candidate["bench_eligible"] and not candidate["governance_valid"]
    assert candidate["regression"]["critical_regressions"]


def test_api_rejects_wrong_blueprint_baseline_and_stale_acceptance(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    other, unused = draft(client, "another-blueprint")
    result = client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True}).json()
    body = {"evaluation_id": result["evaluation_id"], "reason": "Scoped verified baseline."}
    assert client.post(PREFIX + f"/blueprints/{other['id']}/baseline", json=body).status_code == 403
    accepted = client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json=body)
    assert accepted.status_code == 200
    assert client.post(PREFIX + f"/blueprints/{bp['id']}/baseline", json=body).status_code == 409
