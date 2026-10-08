"""Deterministic disposable performance data; no product demo seeding."""
import datetime as dt
import json

from database.schema import AgentBlueprintModel, AuditEventModel, DivisionModel, RunStateModel
from packages.contracts.core import AuditEvent, AuditStatus

DATASETS = {
    "small": {"blueprints": 20, "runs": 50, "audits": 200, "divisions": 10},
    "large": {"blueprints": 200, "runs": 1000, "audits": 5000, "divisions": 200},
}


def seed_workspace_dataset(db, context, size="large"):
    counts = DATASETS[size]
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    with db.session(write=True) as session:
        for index in range(counts["blueprints"]):
            session.add(AgentBlueprintModel(id=f"fixture-bp-{index:05}", organization_id=context.organization_id,
                project_id=context.project_id, name=f"Research {index:05}", slug=f"research-{index:05}",
                description="Disposable dataset", created_by=context.actor.actor_id, created_at=base + dt.timedelta(seconds=index)))
        for index in range(counts["divisions"]):
            session.add(DivisionModel(id=f"fixture-div-{index:05}", organization_id=context.organization_id,
                project_id=context.project_id, name=f"Division {index:05}", slug=f"division-{index:05}", created_at=base + dt.timedelta(seconds=index)))
        for index in range(counts["runs"]):
            # Explicit historical read-only records: absent claims must remain unverified.
            session.add(RunStateModel(id=f"fixture-run-{index:05}", organization_id=context.organization_id,
                project_id=context.project_id, prompt="Disposable historical input", output="Disposable output " * 100,
                model="test/model-a", provider="isolated", status="failed" if index % 10 == 0 else "completed",
                created_at=base + dt.timedelta(seconds=index)))
        for index in range(counts["audits"]):
            event = AuditEvent(event_id=f"fixture-event-{index:05}", schema_version="2.0.0", event_type="fixture.inventory.observed",
                occurred_at=(base + dt.timedelta(seconds=index)).isoformat(), organization_id=context.organization_id,
                project_id=context.project_id, actor_id=context.actor.actor_id, actor_type="user", correlation_id=f"fixture-correlation-{index:05}",
                resource_id=f"fixture-run-{index % counts['runs']:05}", status=AuditStatus.COMPLETED,
                redacted_payload={"source": "disposable_test_fixture"})
            event.integrity_reference = event.calculate_integrity()
            event.attestation = db.evidence_signer.sign("audit_event", event.authenticated_payload())
            session.add(AuditEventModel(id=event.event_id, event_id=event.event_id, event_type=event.event_type,
                schema_version=event.schema_version, occurred_at=base + dt.timedelta(seconds=index),
                organization_id=event.organization_id, project_id=event.project_id, actor_type="user", actor_id=event.actor_id,
                correlation_id=event.correlation_id, resource_id=event.resource_id, status="completed",
                redacted_payload_json=json.dumps(event.redacted_payload), integrity_reference=event.integrity_reference, attestation=event.attestation))
    return counts
