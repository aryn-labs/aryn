"""Live PostgreSQL: additive migration, limited writer and real recovery lineage."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.postgresql.test_workflow_persistence import studio as studio
from tests.integration.test_workflow_execution import workflow as workflow
from tests.integration import test_intelligence_recovery as acceptance
from tests.postgresql.conftest import migrate_to
from database.intelligence_protection import TABLES, MUTABLE_TABLES
from tests.integration.test_studio_api import PREFIX

pytestmark = pytest.mark.postgresql


def test_recovery_capsule_and_isolated_replay(studio, monkeypatch):
    acceptance.test_real_evidence_recovery_capsule_replay_has_no_live_effects(
        studio, monkeypatch
    )


def test_failed_health_cannot_close(studio):
    acceptance.test_action_completed_is_not_recovered_when_health_still_fails(studio)


def test_no_evidence_abstains(studio):
    acceptance.test_no_evidence_abstains_and_cannot_propose(studio)


def test_concurrent_claim_and_signal(studio, monkeypatch):
    acceptance.test_incident_key_and_execution_claim_are_exactly_once_under_contention(
        studio, monkeypatch
    )


def test_internal_sources_keep_workflow_lineage(workflow):
    acceptance.test_real_core_run_and_artifact_sources_keep_exact_workflow_lineage(
        workflow
    )


@pytest.mark.parametrize(
    "attack", ["unapproved", "changed_hash", "changed_proposal", "target_revision"]
)
def test_stale_or_unapproved_actions(studio, attack):
    acceptance.test_unapproved_or_stale_actions_do_not_mutate_demo(studio, attack)


def test_role_and_project_boundaries(studio):
    acceptance.test_scoped_access_pagination_and_viewer_cannot_authorize_recovery(
        studio
    )


def test_revocation_at_effect_commit(studio, monkeypatch):
    acceptance.test_revocation_between_claim_and_effect_is_denied_at_commit(
        studio, monkeypatch
    )


@pytest.mark.parametrize("checkpoint", ["before_effect", "after_effect"])
def test_restart_unknown_requires_reconciliation(studio, monkeypatch, checkpoint):
    acceptance.test_crash_recovery_retains_unknown_without_repeating_effect(
        studio, monkeypatch, checkpoint
    )


def test_corrupted_approval_cannot_authorize(studio):
    acceptance.test_signed_approval_corruption_cannot_authorize_action(studio)


def test_changed_health_cannot_close(studio):
    acceptance.test_changed_health_after_verification_cannot_close(studio)


def test_replay_rejects_escaped_action_trace(studio, monkeypatch):
    acceptance.test_replay_graders_reject_escaped_adapter_and_never_write_live(
        studio, monkeypatch
    )


def test_writer_cannot_change_or_erase_evidence(postgres_db, studio):
    client, db, _, _ = studio
    acceptance.demo_incident(client)
    for table in TABLES:
        for statement in (
            f"UPDATE {table} SET details_json='{{}}'",
            f"DELETE FROM {table}",
            f"TRUNCATE {table}",
        ):
            with pytest.raises(DBAPIError), db.engine.begin() as connection:
                connection.execute(text(statement))
    for table in MUTABLE_TABLES:
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {table}"))
    with pytest.raises(RuntimeError, match="intelligence history"):
        migrate_to(postgres_db.owner, "018_workflow_execution", downgrade=True)
    with postgres_db.owner.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "020_core_automations"
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM relay_incidents")).scalar()
            == 1
        )


def test_unrelated_target_cannot_ground_action(studio):
    acceptance.test_other_disposable_targets_cannot_inflate_incident_coverage(studio)


def test_owner_corruption_stays_unverified(postgres_db, studio):
    client, _, _, _ = studio
    _, _, incident = acceptance.demo_incident(client)
    incident = acceptance.investigated(client, incident)
    source = incident["bundle"]["source_ids"][0]
    with postgres_db.owner.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE evidence_sources DISABLE TRIGGER aryn_evidence_sources_mutation"
            )
        )
        connection.execute(
            text("UPDATE evidence_sources SET blob=:blob WHERE id=:id"),
            {"id": source, "blob": b"forged"},
        )
    bundle = client.get(PREFIX + f"/brief/{incident['bundle_id']}").json()
    assert bundle["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert any(
        i["integrity"] == "UNVERIFIED" and not i["excerpt"]
        for i in bundle["evaluation"]["items"]
    )


def test_additive_upgrade_from_populated_authority(postgres_db):
    # With no new evidence, rollback remains possible without touching history.
    migrate_to(postgres_db.owner, "015_authentication_boundary", downgrade=True)
    with postgres_db.owner.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES ('preserved', 'Preserved', 'preserved', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    migrate_to(postgres_db.owner, "head")
    postgres_db.grant_writer()
    with postgres_db.db.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT id FROM organizations WHERE id='preserved'")
            ).scalar()
            == "preserved"
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM relay_incidents")).scalar()
            == 0
        )
