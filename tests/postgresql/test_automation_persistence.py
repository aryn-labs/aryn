"""Schedules use the same live PostgreSQL non-owner writer as manual execution."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.postgresql.test_workflow_persistence import studio as studio
from tests.integration.test_workflow_execution import workflow as workflow
from tests.integration import test_core_automations as acceptance
from tests.postgresql.conftest import migrate_to
from database.automation_protection import TABLES, MUTABLE_TABLES

pytestmark = pytest.mark.postgresql


def test_scheduled_core_claim(studio):
    acceptance.test_tick_real_claim_pinned_model_usage_and_manual_idempotency(studio)


def test_division_target_scope(studio):
    acceptance.test_division_assignment_preserves_scope_and_rejects_foreign_division(
        studio
    )


def test_scheduled_workflow_review(workflow):
    acceptance.test_workflow_schedule_keeps_three_tasks_review_and_automation_lineage(
        workflow
    )


def test_occurrence_contention(studio):
    acceptance.test_concurrent_tick_and_manual_delivery_admit_once(studio)


def test_schedule_revision_and_approval(studio):
    acceptance.test_schedule_change_invalidates_old_approval_and_paused_tick(studio)


def test_revoked_owner(studio):
    acceptance.test_revoked_owner_pauses_without_dispatch(studio)


def test_revoked_inside_claim(studio, monkeypatch):
    acceptance.test_revocation_inside_claim_rolls_back_before_runtime(
        studio, monkeypatch
    )


@pytest.mark.parametrize("overlap", ["skip", "queue"])
def test_unknown_never_retried(studio, monkeypatch, overlap):
    acceptance.test_unknown_effect_never_retried_and_overlap_requires_reconciliation(
        studio, monkeypatch, overlap
    )


def test_budget_denial(studio):
    acceptance.test_budget_denial_has_no_effect_and_daily_policy_is_real(studio)


def test_actual_admission_day_quota(studio):
    acceptance.test_queued_previous_day_counts_against_actual_admission_day(studio)


def test_planner_authorization_lock_order(studio, monkeypatch):
    acceptance.test_planner_locks_membership_before_definition(studio, monkeypatch)


def test_immutable_schedule_events_and_safe_rollback(studio, postgres_db):
    client, db, _, _ = studio
    definition, _, _ = acceptance.scheduled(studio)
    acceptance.enable(client, definition)
    for table in TABLES:
        for statement in (
            f"UPDATE {table} SET details_json='{{}}'",
            f"DELETE FROM {table}",
            f"TRUNCATE {table}",
        ):
            with pytest.raises(DBAPIError), db.engine.begin() as connection:
                connection.execute(text(statement))
    for table in MUTABLE_TABLES:
        for statement in (f"DELETE FROM {table}", f"TRUNCATE {table}"):
            with pytest.raises(DBAPIError), db.engine.begin() as connection:
                connection.execute(text(statement))
    with pytest.raises(RuntimeError, match="Populated Core"):
        migrate_to(postgres_db.owner, "019_intelligence_recovery", downgrade=True)
    with postgres_db.owner.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "020_core_automations"
        )
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM automation_definitions")
            ).scalar()
            == 1
        )
