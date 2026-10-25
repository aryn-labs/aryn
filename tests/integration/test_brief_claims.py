"""Bounded claims use verified domain facts and never invent missing metrics."""

import pytest
from tests.integration.test_studio_api import studio as studio, PREFIX, draft
from tests.integration.test_workflow_execution import workflow as workflow, start
from tests.integration.test_intelligence_recovery import post
from tests.integration.test_brief_local_evidence import bundle
from tests.integration.test_operational_governance import operational


@pytest.mark.parametrize("failed", [False, True])
def test_evaluation_claim_preserves_verified_failure_and_exact_subject(studio, failed):
    client, db, runtime, app = studio
    _, version = draft(client, "evidence-evaluation")
    runtime.fail = failed
    result = post(client, f"/versions/{version['id']}/bench", {"allow_remote_model": True})
    source = post(client, "/brief/sources", {"title": "Verified evaluation", "source_ref": {
        "kind": "evaluation", "id": result["evaluation_id"]}})
    hypothesis = {"question": "Did this exact verified evaluation pass?", "predicate": "evaluation_passed",
        "subject_id": result["evaluation_id"]}
    assert bundle(client, source, hypothesis)["evaluation"]["status"] == ("CONFLICTING" if failed else "SUPPORTED")
    hypothesis["subject_id"] = "another_evaluation"
    assert bundle(client, source, hypothesis)["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize("predicate,metric,maximum,expected", [
    ("configuration_matches", None, None, "SUPPORTED"),
    ("configuration_matches", None, None, "CONFLICTING"),
    ("resource_within_limit", "latency_ms", 1, "SUPPORTED"),
    ("resource_within_limit", "latency_ms", 0, "CONFLICTING"),
    ("resource_within_limit", "memory_bytes", 134217728, "INSUFFICIENT_EVIDENCE"),
])
def test_configuration_and_resource_claims_distinguish_observations_from_limits(studio, predicate, metric, maximum, expected):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    observed = post(client, f"/relay/targets/{target['id']}/observe")
    hypothesis = {"question": "Does the exact captured operational observation support this bounded claim?", "predicate": predicate}
    if predicate == "configuration_matches":
        hypothesis.update(target_id=target["id"], text=target["configuration_hash"] if expected == "SUPPORTED" else "0" * 64)
    else:
        hypothesis.update(subject_id=target["id"], metric=metric, maximum=maximum)
    evaluated = bundle(client, observed["source"], hypothesis)
    assert evaluated["evaluation"]["status"] == expected
    assert not runtime.requests and not adapter.effects


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_workflow_completion_claim_uses_actual_human_review_state(workflow, decision):
    client, db, runtime, app, saved, version = workflow
    run = start(workflow)
    artifact = client.get(PREFIX + "/outputs/" + run["artifact_id"]).json()
    post(client, f"/workflow-runs/{run['id']}/review", {"digest": artifact["digest"], "decision": decision,
        "reason": "Review the exact workflow artifact before evaluating its completion claim."})
    source = post(client, "/brief/sources", {"title": "Verified workflow state", "source_ref": {"kind": "workflow", "id": run["id"]}})
    evaluated = bundle(client, source, {"question": "Did this exact workflow complete?", "predicate": "workflow_completed", "subject_id": run["id"]})
    assert evaluated["evaluation"]["status"] == ("SUPPORTED" if decision == "accepted" else "CONFLICTING")
