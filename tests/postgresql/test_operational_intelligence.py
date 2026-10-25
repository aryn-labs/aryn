"""Current intelligence contracts on a real restricted PostgreSQL writer."""

import pytest
from sqlalchemy import text
from tests.postgresql.test_workflow_persistence import studio as studio
from tests.postgresql.conftest import migrate_to
from tests.integration import test_operational_governance as operational
from tests.integration import test_bench_suite_authoring as suites
from tests.integration import test_brief_local_evidence as evidence
from tests.integration import test_brief_interpretation as interpretation
from tests.integration import test_brief_claims as claims
from tests.integration.test_workflow_execution import workflow as workflow
from tests.integration import test_intelligence_recovery as legacy
from tests.integration.test_studio_api import PREFIX

pytestmark = pytest.mark.postgresql


def test_reviewed_suite_executes_with_restricted_writer(studio):
    suites.test_authored_suite_requires_exact_review_and_runs_existing_engine(studio)


def test_failing_suite_and_candidate_review_preserve_promotion_gate(studio):
    suites.test_deliberate_regression_stays_rejected_and_failure_requires_human_candidate_review(studio)


def test_current_operational_admission(studio):
    operational.test_operational_admission_and_legacy_fixture_mutation_denial(studio)


def test_cancellation_before_dispatch(studio, monkeypatch):
    operational.test_cancellation_wins_before_dispatch_and_never_runs_an_effect(studio, monkeypatch)


def test_unknown_history_survives_reconciliation(studio, monkeypatch):
    operational.test_unknown_outcome_idempotency_and_reconciliation_never_redrive(studio, monkeypatch)


@pytest.mark.parametrize("blocking", [False, True])
def test_capsule_health_and_reviewed_candidate(studio, blocking):
    operational.test_settled_capsules_capture_independent_health_and_reviewed_regression_candidate(studio, blocking)


@pytest.mark.parametrize("change", ["modify", "remove", "revoke"])
def test_physical_evidence_authority(studio, tmp_path, change):
    evidence.test_physical_file_change_or_revocation_invalidates_claim(studio, tmp_path, change)


def test_informational_interpretation_idempotency(studio):
    interpretation.test_interpretation_is_scoped_informational_signed_and_idempotent(studio)


@pytest.mark.parametrize("failed", [False, True])
def test_verified_evaluation_claim(studio, failed):
    claims.test_evaluation_claim_preserves_verified_failure_and_exact_subject(studio, failed)


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_reviewed_workflow_claim(workflow, decision):
    claims.test_workflow_completion_claim_uses_actual_human_review_state(workflow, decision)


def test_additive_intelligence_migrations_preserve_signed_legacy_capsule(postgres_db, studio):
    client, db, runtime, app = studio
    _, _, incident = legacy.demo_incident(client)
    incident = legacy.proposed(client, legacy.investigated(client, incident))
    legacy.approved(client, incident)
    incident = legacy.post(client, f"/relay/{incident['id']}/execute", legacy.execution_body(incident))
    closed = legacy.post(client, f"/relay/{incident['id']}/close", {"expected_revision": incident["revision"]})
    with postgres_db.owner.connect() as connection:
        before = connection.execute(text("SELECT details_json,attestation FROM relay_capsules WHERE id=:id"), {"id": closed["capsule_id"]}).one()
    migrate_to(postgres_db.owner, "024_project_metadata", downgrade=True)
    migrate_to(postgres_db.owner, "head")
    postgres_db.grant_writer()
    with postgres_db.owner.connect() as connection:
        after = connection.execute(text("SELECT details_json,attestation FROM relay_capsules WHERE id=:id"), {"id": closed["capsule_id"]}).one()
    assert before == after
    assert client.get(PREFIX + "/relay/capsules/" + closed["capsule_id"]).json() == closed["capsule"]
    assert legacy.post(client, f"/bench/capsules/{closed['capsule_id']}/replay")["live_write_calls"] == 0
