"""Real restricted-writer PostgreSQL acceptance, never a SQLite fallback."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from services.api.studio import create_app
from tests.studio_runtime import IsolatedTestRuntime
from tests.integration.test_studio_api import ORIGIN
from tests.integration.test_workflow_execution import workflow as workflow
from tests.integration.test_workflow_execution import (
    test_three_tasks_exact_handoff_review_restart_download as golden,
    test_invalid_graph_authoritative as invalid,
    test_stale_cas_hash_approval_review_role_and_tenant as scope_and_role,
    test_execution_failure_and_static_isolation as boundary,
    test_concurrent_start_and_review_exactly_once as concurrency,
    test_restart_unknown_claim_no_retry_and_waiting_artifact_survives as recovery,
)
from tests.postgresql.conftest import migrate_to
from tests.integration.test_workflow_execution import start
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgresql


@pytest.fixture
def studio(postgres_db):
    db = postgres_db.db
    runtime = IsolatedTestRuntime()
    app = create_app(db, runtime, testing=True)
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
        token = client.post("/api/session", json={}, headers={"Origin": ORIGIN}).json()[
            "csrf"
        ]
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": token})
        yield client, db, runtime, app


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_postgres_three_tasks_and_review(workflow, decision):
    golden(workflow, decision)


@pytest.mark.parametrize(
    "attack", ["port", "cycle", "schema", "missing", "review_bypass"]
)
def test_postgres_graph_rejected(workflow, attack):
    invalid(workflow, attack)


def test_postgres_scope_and_reviewer(workflow):
    scope_and_role(workflow)


def test_postgres_start_and_review_contention(workflow):
    concurrency(workflow)


def test_postgres_recovery_fencing_retains_unknown(workflow):
    recovery(workflow)


@pytest.mark.parametrize("attack", ["script", "unknown", "budget", "sandbox"])
def test_postgres_execution_boundary(workflow, monkeypatch, attack):
    boundary(workflow, monkeypatch, attack)


def test_postgres_populated_downgrade_refused(postgres_db, workflow):
    with pytest.raises(RuntimeError, match="workflow evidence"):
        migrate_to(postgres_db.owner, "017_agent_editor", downgrade=True)
    with postgres_db.owner.connect() as c:
        assert (
            c.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "018_workflow_execution"
        )
        assert c.execute(text("SELECT COUNT(*) FROM workflow_versions")).scalar() == 1


@pytest.mark.parametrize("column", ["blob", "mime"])
def test_postgres_owner_corruption_and_writer_rejection(postgres_db, workflow, column):
    client, db, _, _, _, _ = workflow
    run = start(workflow)
    with pytest.raises(DBAPIError), db.engine.begin() as c:
        c.execute(
            text("UPDATE workflow_artifacts SET blob=:blob WHERE id=:id"),
            {"blob": b"invalid", "id": run["artifact_id"]},
        )
    with postgres_db.owner.begin() as c:
        c.execute(
            text(
                "ALTER TABLE workflow_artifacts DISABLE TRIGGER aryn_workflow_artifacts_mutation"
            )
        )
        if column == "blob":
            c.execute(
                text("UPDATE workflow_artifacts SET blob=:blob WHERE id=:id"),
                {"blob": b"invalid", "id": run["artifact_id"]},
            )
        else:
            c.execute(
                text(
                    "UPDATE workflow_artifacts SET details_json=replace(details_json, 'text/html', 'application/json') WHERE id=:id"
                ),
                {"id": run["artifact_id"]},
            )
    from tests.integration.test_studio_api import PREFIX

    assert (
        client.get(PREFIX + f"/outputs/{run['artifact_id']}/download").status_code
        != 200
    )
