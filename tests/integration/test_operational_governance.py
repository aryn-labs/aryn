"""Production Core governance over an explicit protocol transport double."""

import copy
import time
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
import pytest
from tests.integration.test_studio_api import studio as studio, PREFIX
from tests.integration.test_intelligence_recovery import post, investigated, approved, execution_body
from tests.operational_fixtures import OperationalProtocolDouble
from packages.tool_adapters.operational import OperationalBoundaryError
from modules.core.records import digest
from modules.core.history import HistoryUnverifiedError


def operational(studio):
    client, db, runtime, app = studio
    adapter = OperationalProtocolDouble()
    app.state.brief.targets = app.state.relay.targets = adapter
    target = post(client, "/relay/targets", {"binding_id": "test_disposable_service", "name": "Protocol double target"})["target"]
    return adapter, target


def propose(client, adapter, target, *, blocking=False):
    adapter.fault(blocking=blocking)
    incident = post(client, "/relay/signals", {"target_id": target["id"], "dedup_key": "server-derived"})
    incident = investigated(client, incident)
    return post(client, f"/relay/{incident['id']}/proposals", {"expected_revision": incident["revision"],
        "action": "restart_service", "target_id": target["id"], "target_revision": adapter.state["generation"],
        "bundle_id": incident["bundle_id"], "reason": "Only the Core-approved stopped process may be started."})


def test_operational_admission_and_legacy_fixture_mutation_denial(studio):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    incident = propose(client, adapter, target)
    response = client.post(PREFIX + f"/relay/{incident['id']}/execute", json=execution_body(incident))
    assert response.status_code in {403, 409} and not adapter.effects
    assert client.post(PREFIX + "/relay/demo-fixtures/" + target["id"], json={
        "expected_revision": adapter.state["generation"], "running": True, "blocking_fault": False}).status_code == 409
    approved(client, incident)
    recovered = post(client, f"/relay/{incident['id']}/execute", execution_body(incident))
    assert recovered["status"] == "RECOVERED" and len(adapter.effects) == 1
    admission = recovered["execution"]["admission"]
    assert db.evidence_signer.verify("relay_operational_action", admission["payload"], admission["attestation"])
    assert admission["payload"]["execution_id"] == recovered["execution_id"]
    assert admission["payload"]["configuration_hash"] == target["configuration_hash"]
    assert not runtime.requests


@pytest.mark.parametrize("drift", ["revoked", "expired", "binding", "instance"])
def test_review_drift_denies_before_external_effect(studio, monkeypatch, drift):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    incident = propose(client, adapter, target)
    approved(client, incident)
    if drift == "revoked":
        post(client, f"/relay/targets/{target['id']}/grant", {"expected_configuration_hash": target["configuration_hash"], "enabled": False})
    elif drift == "expired":
        monkeypatch.setattr("modules.relay.targets.time", SimpleNamespace(time=lambda: time.time() + 301, monotonic=time.monotonic))
    elif drift == "binding":
        adapter.bindings["test_disposable_service"]["image_id"] = "sha256:" + "f" * 64
    else:
        adapter.state["instance"] = "f" * 32
    response = client.post(PREFIX + f"/relay/{incident['id']}/execute", json=execution_body(incident))
    assert response.status_code == 409, response.text
    assert not adapter.effects


def test_cancellation_wins_before_dispatch_and_never_runs_an_effect(studio, monkeypatch):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    incident = propose(client, adapter, target)
    approved(client, incident)
    claimed, release = threading.Event(), threading.Event()
    original = app.state.relay.apply_service

    def wait_before_dispatch(ctx, identifier):
        claimed.set()
        assert release.wait(10)
        return original(ctx, identifier)

    monkeypatch.setattr(app.state.relay, "apply_service", wait_before_dispatch)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, PREFIX + f"/relay/{incident['id']}/execute", json=execution_body(incident))
        try:
            assert claimed.wait(10)
            current = client.get(PREFIX + "/relay/" + incident["id"]).json()
            cancelled = post(client, f"/relay/{incident['id']}/cancel", {"expected_revision": current["revision"]})
            assert cancelled["cancellation_confirmed"]
        finally:
            release.set()
        result = pending.result(timeout=10)
    assert result.status_code == 200, result.text
    assert result.json()["execution"]["error_code"] == "cancelled_before_dispatch"
    assert not adapter.effects


def test_unknown_outcome_idempotency_and_reconciliation_never_redrive(studio, monkeypatch):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    incident = propose(client, adapter, target)
    approved(client, incident)
    original = app.state.relay.verify
    monkeypatch.setattr(app.state.relay, "verify", lambda *args, **kwargs: (_ for _ in ()).throw(OperationalBoundaryError("Observation unavailable.")))
    unknown = post(client, f"/relay/{incident['id']}/execute", execution_body(incident))
    assert unknown["status"] == "OUTCOME_UNKNOWN" and len(adapter.effects) == 1
    observe = adapter.observe
    monkeypatch.setattr(adapter, "observe", lambda *args, **kwargs: (_ for _ in ()).throw(OperationalBoundaryError("Offline.")))
    repeated = post(client, f"/relay/{incident['id']}/execute", execution_body(incident))
    assert repeated["execution_id"] == unknown["execution_id"] and len(adapter.effects) == 1
    cancelled = post(client, f"/relay/{incident['id']}/cancel", {"expected_revision": unknown["revision"]})
    assert not cancelled["cancellation_confirmed"] and len(adapter.effects) == 1
    captured = post(client, f"/relay/{incident['id']}/capsule", {"expected_revision": unknown["revision"]})
    assert captured["capsule"]["outcome"] == "OUTCOME_UNKNOWN"
    assert captured["capsule"]["recovered"] is None and captured["capsule"]["verification_id"] is None
    capsule_id = captured["capsule_id"]
    replayed = post(client, f"/bench/capsules/{capsule_id}/replay")
    assert replayed["source_outcome"] == "OUTCOME_UNKNOWN" and replayed["live_write_calls"] == 0
    monkeypatch.setattr(adapter, "observe", observe)
    monkeypatch.setattr(app.state.relay, "verify", original)
    reconciled = post(client, f"/relay/{incident['id']}/reconcile", {"expected_revision": captured["revision"]})
    assert reconciled["status"] == "RECOVERED" and len(adapter.effects) == 1
    historical = client.get(PREFIX + "/relay/capsules/" + capsule_id)
    assert historical.status_code == 200 and historical.json()["outcome"] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("blocking", [False, True])
def test_settled_capsules_capture_independent_health_and_reviewed_regression_candidate(studio, blocking):
    from tests.integration.test_bench_suite_authoring import declaration, author
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    incident = propose(client, adapter, target, blocking=blocking)
    approved(client, incident)
    settled = post(client, f"/relay/{incident['id']}/execute", execution_body(incident))
    captured = post(client, f"/relay/{incident['id']}/capsule", {"expected_revision": settled["revision"]})
    capsule = captured["capsule"]
    assert capsule["outcome"] == ("DEGRADED" if blocking else "RECOVERED")
    assert capsule["recovered"] is not blocking
    assert capsule["lineage"]["verification_observation"]["payload"]["healthy"] is not blocking
    replay = post(client, f"/bench/capsules/{capsule['id']}/replay")
    assert replay["live_write_calls"] == 0 and not replay["promotion_evidence"] and len(adapter.effects) == 1
    candidate = post(client, "/bench/scenario-candidates", {"source_kind": "capsule", "source_id": capsule["id"],
        "scenario": declaration()["scenarios"][0], "reason": "Explicitly review this captured incident before authoring a regression."})
    body = declaration(family_key="captured_incident", candidate_id=candidate["id"])
    assert client.post(PREFIX + "/bench/suite-versions", json=body).status_code in {403, 409}
    post(client, f"/bench/scenario-candidates/{candidate['id']}/review", {"expected_digest": candidate["digest"],
        "reason": "Human review of the exact safe declaration; no live replay authority."})
    assert author(client, body)["candidate_id"] == candidate["id"]


@pytest.mark.parametrize("checkpoint", ["signal", "investigation", "proposal", "execution", "bundle", "verification", "verification_observation"])
def test_capsule_rejects_signed_checkpoints_from_a_different_incident(studio, checkpoint):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    capsules = []
    for index in range(2):
        incident = propose(client, adapter, target)
        approved(client, incident)
        settled = post(client, f"/relay/{incident['id']}/execute", execution_body(incident, f"capsule-{index}"))
        captured = post(client, f"/relay/{incident['id']}/capsule", {"expected_revision": settled["revision"]})
        capsules.append(captured["capsule"])
    forged = copy.deepcopy(capsules[0])
    forged["lineage"][checkpoint] = capsules[1]["lineage"][checkpoint]
    forged["digest"] = digest({key: value for key, value in forged.items() if key != "digest"})
    from services.api.studio import DEV_ACTOR
    ctx = app.state.binder.create_trusted_context(DEV_ACTOR, target["organization_id"], target["project_id"])
    with db.session() as session, pytest.raises(HistoryUnverifiedError):
        app.state.relay.validate_operational_capsule(session, ctx, forged)
    assert len(adapter.effects) == 2


def test_target_hourly_quota_counts_durable_claims_and_denies_another_effect(studio):
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    from packages.tool_adapters.operational import OperationalTargets
    physical = copy.deepcopy(next(iter(adapter.bindings.values())))
    alias = {**physical, "binding_id": "another_service_alias"}
    with pytest.raises(ValueError, match="physical operational target"):
        OperationalTargets({"targets": [physical, alias]})
    # A renamed operator binding after configuration reload must not create a
    # second durable identity for the same physical process and reset its quota.
    adapter.bindings[alias["binding_id"]] = alias
    denied_alias = client.post(PREFIX + "/relay/targets", json={"binding_id": alias["binding_id"], "name": "Denied alias"})
    assert denied_alias.status_code == 409 and not adapter.effects
    for index in range(6):
        incident = propose(client, adapter, target)
        approved(client, incident)
        assert post(client, f"/relay/{incident['id']}/execute", execution_body(incident, f"quota-{index}"))["status"] == "RECOVERED"
    adapter.fault()
    incident = post(client, "/relay/signals", {"target_id": target["id"], "dedup_key": "quota"})
    incident = investigated(client, incident)
    response = client.post(PREFIX + f"/relay/{incident['id']}/proposals", json={"expected_revision": incident["revision"],
        "action": "restart_service", "target_id": target["id"], "target_revision": adapter.state["generation"],
        "bundle_id": incident["bundle_id"], "reason": "Quota exhaustion must deny this effect."})
    assert response.status_code == 409 and len(adapter.effects) == 6


def test_unresolved_claim_remains_a_fence_after_quota_window(studio, monkeypatch):
    import datetime
    client, db, runtime, app = studio
    adapter, target = operational(studio)
    incident = propose(client, adapter, target)
    approved(client, incident)
    monkeypatch.setattr(app.state.relay, "verify", lambda *args, **kwargs: (_ for _ in ()).throw(OperationalBoundaryError("Unavailable.")))
    unknown = post(client, f"/relay/{incident['id']}/execute", execution_body(incident))
    assert unknown["status"] == "OUTCOME_UNKNOWN"

    class Later(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime.now(tz) + datetime.timedelta(hours=2)

    monkeypatch.setattr("modules.relay.targets.datetime", SimpleNamespace(datetime=Later,
        timezone=datetime.timezone, timedelta=datetime.timedelta))
    adapter.fault()
    next_incident = post(client, "/relay/signals", {"target_id": target["id"], "dedup_key": "still_unresolved"})
    next_incident = investigated(client, next_incident)
    response = client.post(PREFIX + f"/relay/{next_incident['id']}/proposals", json={"expected_revision": next_incident["revision"],
        "action": "restart_service", "target_id": target["id"], "target_revision": adapter.state["generation"],
        "bundle_id": next_incident["bundle_id"], "reason": "An unresolved effect must remain fenced after one hour."})
    assert response.status_code == 409 and len(adapter.effects) == 1
    # A database writer cannot hide an unresolved claim by changing SQL query
    # mirrors. The signed target anchor resolves the exact protected record.
    from sqlalchemy import text
    with db.session(write=True) as session:
        session.execute(text("UPDATE relay_executions SET status='verified', created_at=:old WHERE id=:id"),
            {"old": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3), "id": unknown["execution_id"]})
    repeated = client.post(PREFIX + f"/relay/{next_incident['id']}/proposals", json={"expected_revision": next_incident["revision"],
        "action": "restart_service", "target_id": target["id"], "target_revision": adapter.state["generation"],
        "bundle_id": next_incident["bundle_id"], "reason": "Tampered SQL mirrors cannot hide the protected admission."})
    assert repeated.status_code == 409 and len(adapter.effects) == 1


@pytest.mark.parametrize("field,value", [
    ("NetworkMode", "host"), ("ReadonlyRootfs", False), ("Privileged", True),
    ("Memory", 0), ("MemorySwap", -1), ("NanoCpus", 0), ("PidsLimit", -1),
    ("CapAdd", ["SYS_ADMIN"]), ("CapDrop", []), ("SecurityOpt", []),
    ("PidMode", "host"), ("IpcMode", "host"), ("Binds", ["/:/host"]),
    ("Tmpfs", {"/opt/aryn": "rw"}), ("PublishAllPorts", True), ("UsernsMode", "host"),
])
def test_target_isolation_drift_is_not_executable(field, value):
    adapter = OperationalProtocolDouble()
    adapter.inspect_data = copy.deepcopy(adapter.inspect_data)
    adapter.inspect_data["HostConfig"][field] = value
    with pytest.raises(OperationalBoundaryError):
        adapter.inspect(next(iter(adapter.bindings.values())))
    assert not adapter.effects
