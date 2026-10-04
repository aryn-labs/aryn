import json
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from database.connection import DatabaseManager, create_db_engine, init_db
from database.repositories.organization_repo import OrganizationRepository
from database.schema import (
    AgentAssignmentModel,
    RunStateModel,
    UsageBudgetModel,
)
from services.api.studio import (
    COOKIE,
    DEV_ACTOR,
    DEV_ORG,
    DEV_PROJECT,
    create_app,
    migrate,
)
from tests.studio_runtime import IsolatedTestRuntime

ORIGIN = "http://127.0.0.1:8710"
PREFIX = f"/api/projects/{DEV_PROJECT}"


@pytest.fixture
def studio(tmp_path):
    db = DatabaseManager(create_db_engine(f"sqlite:///{tmp_path / 'studio.sqlite3'}"))
    init_db(db.engine)
    runtime = IsolatedTestRuntime()
    app = create_app(db, runtime, testing=True)
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        client.headers.update(
            {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]}
        )
        yield client, db, runtime, app
    db.engine.dispose()


def draft(client, slug="research-test"):
    bp = client.post(
        PREFIX + "/blueprints",
        json={
            "name": "Agent riset tes",
            "slug": slug,
            "description": "Pengujian terisolasi",
        },
    )
    assert bp.status_code == 201, bp.text
    bp = bp.json()
    v = client.post(
        PREFIX + f"/blueprints/{bp['id']}/versions",
        json={
            "version_number": "1.0.0",
            "system_prompt": "Follow research safety guidelines and abstain without evidence.",
            "model": "stealth/space-bunny-alpha",
            "temperature": 0.2,
            "max_tokens": 512,
        },
    )
    assert v.status_code == 201, v.text
    return bp, v.json()


def promoted(client, bp, v):
    bench = client.post(
        PREFIX + f"/versions/{v['id']}/bench", json={"allow_remote_model": True}
    )
    assert bench.status_code == 200 and bench.json()["passed"], bench.text
    approval = client.post(
        PREFIX + f"/versions/{v['id']}/approve",
        json={
            "payload_hash": v["payload_hash"],
            "comments": "Lulus evaluasi terisolasi.",
        },
    )
    assert approval.status_code == 200, approval.text
    assert (
        client.post(PREFIX + f"/versions/{v['id']}/publish", json={}).status_code == 200
    )
    assignment = client.post(
        PREFIX + "/assignments",
        json={
            "blueprint_id": bp["id"],
            "version_id": v["id"],
            "role_name": "Peneliti tes",
        },
    )
    assert assignment.status_code == 201, assignment.text
    return assignment.json()


def test_full_http_lifecycle_persistence_usage_and_idempotency(studio):
    client, db, runtime, app = studio
    workspace = client.get("/api/workspace")
    assert workspace.status_code == 200 and workspace.json()["mode"] == "isolated-test"
    bp, v = draft(client)
    assignment = promoted(client, bp, v)
    payload = {
        "assignment_id": assignment["id"],
        "prompt": "Jelaskan likuiditas dan solvabilitas.",
        "idempotency_key": secrets.token_hex(16),
        "allow_remote_model": True,
    }
    result = client.post(PREFIX + "/runs", json=payload)
    assert result.status_code == 200, result.text
    run_id = result.json()["run_id"]
    repeat = client.post(PREFIX + "/runs", json=payload)
    assert repeat.status_code == 200 and repeat.json()["id"] == run_id
    assert (
        len(runtime.requests) == 5
    )  # 4 real Bench scenarios on the isolated test double + 1 research
    assert all(r.temperature == 0.2 and r.max_tokens == 512 for r in runtime.requests)
    assert (
        client.post(
            PREFIX + "/runs", json={**payload, "prompt": "Changed request input"}
        ).status_code
        == 409
    )
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert snapshot["runs"][0]["total_tokens"] == 50
    assert snapshot["budget"]["cumulative_tokens"] == 250
    assert snapshot["evaluations"][0]["provenance"]["payload_hash"] == v["payload_hash"]
    assert snapshot["evaluations"][0]["details"][0]["actual_model"] == v["model"]
    assert {
        "core.run.initiated",
        "core.run.completed",
        "studio.run.assignment",
    }.issubset({e["event_type"] for e in snapshot["audit"]})
    assert "identity_token" not in json.dumps(snapshot)
    # Application restart changes sessions/signing key, while persisted configuration/results remain.
    other = create_app(db, IsolatedTestRuntime(), testing=True)
    with TestClient(other, base_url=ORIGIN, client=("127.0.0.1", 1)) as restarted:
        token = restarted.post(
            "/api/session", json={}, headers={"Origin": ORIGIN}
        ).json()["csrf"]
        restarted.headers.update({"Origin": ORIGIN, "X-CSRF-Token": token})
        assert restarted.get(PREFIX + "/snapshot").json()["runs"][0]["id"] == run_id


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": ORIGIN, "X-CSRF-Token": "forged"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
        {"Host": "evil.example"},
    ],
)
def test_origin_csrf_fetch_metadata_and_host_denial(studio, headers):
    client, *_ = studio
    response = client.post(
        PREFIX + "/blueprints",
        json={"name": "Unsafe", "slug": "unsafe"},
        headers=headers,
    )
    assert response.status_code == 403


def test_no_session_remote_client_and_identity_forgery(studio):
    client, db, runtime, app = studio
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as anonymous:
        assert anonymous.get(PREFIX + "/snapshot").status_code == 401
        assert (
            anonymous.post(
                "/api/session",
                json={"actor_id": "root", "role": "admin"},
                headers={"Origin": ORIGIN},
            ).status_code
            == 422
        )
        assert anonymous.post("/api/session", json={}).status_code == 403
    with TestClient(app, base_url=ORIGIN, client=("192.168.1.20", 1)) as external:
        assert external.get("/").status_code == 403
    assert (
        client.post(
            PREFIX + "/blueprints",
            json={"name": "Forgery", "slug": "forgery", "actor_id": "root"},
        ).status_code
        == 422
    )
    token = client.cookies.get(COOKIE)
    app.state.sessions[token]["expires"] = 0
    assert client.get(PREFIX + "/snapshot").status_code == 401


def test_validation_duplicates_and_cross_project_reads(studio):
    client, *_ = studio
    bp, v = draft(client)
    assert (
        client.post(
            PREFIX + "/blueprints",
            json={"name": "Agent riset tes", "slug": "research-test"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            PREFIX + "/blueprints", json={"name": "a", "slug": "invalid slug"}
        ).status_code
        == 422
    )
    assert client.get("/api/projects/unauthorized/snapshot").status_code == 403
    assert (
        client.post(
            PREFIX + f"/blueprints/{bp['id']}/versions",
            json={
                "version_number": "2.0.0",
                "system_prompt": "Research only, never run host commands.",
                "model": "mock-fast",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            PREFIX + f"/blueprints/{bp['id']}/versions",
            json={
                "version_number": "2.0.0",
                "system_prompt": "Research only, never run host commands.",
                "model": v["model"],
                "tool_grants": ["terminal"],
            },
        ).status_code
        == 422
    )


def test_bench_failure_blocks_approval_publication_and_assignment(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    assert (
        client.post(
            PREFIX + f"/versions/{v['id']}/approve",
            json={"comments": "No evaluation yet", "payload_hash": v["payload_hash"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            PREFIX + f"/versions/{v['id']}/bench", json={"allow_remote_model": False}
        ).status_code
        == 422
    )
    runtime.fail = True
    result = client.post(
        PREFIX + f"/versions/{v['id']}/bench", json={"allow_remote_model": True}
    )
    assert result.status_code == 200 and result.json()["passed"] is False
    assert result.json()["scenario_results"][0]["failure_reason"]
    assert (
        client.post(
            PREFIX + f"/versions/{v['id']}/approve",
            json={
                "comments": "Denied despite failure",
                "payload_hash": v["payload_hash"],
            },
        ).status_code
        == 409
    )
    assert (
        client.post(PREFIX + f"/versions/{v['id']}/publish", json={}).status_code == 409
    )
    assert (
        client.post(
            PREFIX + "/assignments",
            json={
                "blueprint_id": bp["id"],
                "version_id": v["id"],
                "role_name": "Unpublished",
            },
        ).status_code
        == 409
    )


def test_hash_tamper_stale_pass_and_unapproved_publication(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    bench_path = PREFIX + f"/versions/{v['id']}/bench"
    assert client.post(bench_path, json={"allow_remote_model": True}).json()["passed"]
    assert (
        client.post(PREFIX + f"/versions/{v['id']}/publish", json={}).status_code == 409
    )
    assert (
        client.post(
            PREFIX + f"/versions/{v['id']}/approve",
            json={"comments": "Hash is tampered", "payload_hash": "a" * 64},
        ).status_code
        == 409
    )
    runtime.fail = True
    assert not client.post(bench_path, json={"allow_remote_model": True}).json()[
        "passed"
    ]
    assert (
        client.post(
            PREFIX + f"/versions/{v['id']}/approve",
            json={
                "comments": "Stale evaluation rejected",
                "payload_hash": v["payload_hash"],
            },
        ).status_code
        == 409
    )


def test_runtime_disconnected_or_tools_enabled_fail_closed(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    for online, tools in [(False, []), (True, ["web"]), (True, ["terminal"])]:
        runtime.online = online
        runtime.tools = tools
        assert (
            client.post(
                PREFIX + f"/versions/{v['id']}/bench", json={"allow_remote_model": True}
            ).status_code
            == 503
        )
        assert not client.get("/api/workspace").json()["runtime"]["ready"]
    assert not runtime.requests


def test_budget_includes_input_and_denies_before_bench_or_run_dispatch(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    assignment = promoted(client, bp, v)
    _, other = draft(client, "budget-denied")
    with db.session() as s:
        budget = (
            s.query(UsageBudgetModel)
            .filter_by(organization_id=DEV_ORG, project_id=DEV_PROJECT)
            .one()
        )
        budget.max_tokens_per_run = 512
    assert (
        client.post(
            PREFIX + f"/versions/{other['id']}/bench", json={"allow_remote_model": True}
        ).status_code
        == 403
    )
    assert (
        client.post(
            PREFIX + "/runs",
            json={
                "assignment_id": assignment["id"],
                "prompt": "Explain research concepts",
                "idempotency_key": secrets.token_hex(16),
                "allow_remote_model": True,
            },
        ).status_code
        == 403
    )
    assert len(runtime.requests) == 4
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert len(snapshot["evaluations"]) == 1
    assert snapshot["runs"] == []


def test_role_revocation_is_immediate_and_persists_restart(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    with db.session() as s:
        repo = OrganizationRepository(s)
        member = repo.get_member(DEV_ORG, DEV_ACTOR)
        member.role = "viewer"
        repo.add_project_member(DEV_PROJECT, DEV_ACTOR, role="viewer")
    assert client.get(PREFIX + "/snapshot").status_code == 200
    assert (
        client.post(
            PREFIX + "/blueprints", json={"name": "Denied", "slug": "denied"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            PREFIX + f"/versions/{v['id']}/approve",
            json={
                "comments": "Viewer cannot approve",
                "payload_hash": v["payload_hash"],
            },
        ).status_code
        == 403
    )
    with db.session() as s:
        OrganizationRepository(s).revoke_member(DEV_ORG, DEV_ACTOR)
    create_app(db, runtime, testing=True)
    assert client.get(PREFIX + "/snapshot").status_code == 403


def test_blueprint_mismatch_and_inactive_assignment(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    assignment = promoted(client, bp, v)
    other, _ = draft(client, "another-blueprint")
    assert (
        client.post(
            PREFIX + "/assignments",
            json={
                "blueprint_id": other["id"],
                "version_id": v["id"],
                "role_name": "Mismatched",
            },
        ).status_code
        == 409
    )
    with db.session() as s:
        s.get(AgentAssignmentModel, assignment["id"]).status = "suspended"
    result = client.post(
        PREFIX + "/runs",
        json={
            "assignment_id": assignment["id"],
            "prompt": "Explain research concepts",
            "idempotency_key": secrets.token_hex(16),
            "allow_remote_model": True,
        },
    )
    assert result.status_code == 403 and len(runtime.requests) == 4


def test_output_html_remains_data_and_failed_runtime_not_completed(studio):
    client, db, runtime, app = studio
    bp, v = draft(client)
    assignment = promoted(client, bp, v)
    runtime.status = __import__(
        "packages.contracts.runtime", fromlist=["RunStatus"]
    ).RunStatus.FAILED
    # Core must persist failed, rather than mark a non-completed response as completed.
    response = client.post(
        PREFIX + "/runs",
        json={
            "assignment_id": assignment["id"],
            "prompt": "No runtime completion",
            "idempotency_key": secrets.token_hex(16),
            "allow_remote_model": True,
        },
    )
    assert response.status_code == 502 and "message" in response.json()
    with db.session() as s:
        assert s.query(RunStateModel).one().status == "failed"


def test_schema_upgrade_004_retains_data(tmp_path):
    from alembic import command
    from alembic.config import Config

    from services.api.studio import ROOT

    engine = create_db_engine(f"sqlite:///{tmp_path / 'migration.sqlite3'}")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "004_project_memberships")
        connection.exec_driver_sql(
            "INSERT INTO organizations (id,name,slug,created_at,updated_at) VALUES ('kept','Kept','kept',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
    migrate(engine)
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT name FROM organizations WHERE id='kept'"
            ).scalar()
            == "Kept"
        )
        assert "provenance_json" in {
            r[1]
            for r in connection.exec_driver_sql("PRAGMA table_info(bench_evaluations)")
        }
    engine.dispose()


def test_snapshot_cannot_present_tampered_configuration_as_eligible(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    assignment = promoted(client, bp, version)
    valid = client.get(PREFIX + "/snapshot").json()
    assert valid["versions"][0]["governance_valid"]
    assert valid["evaluations"][0]["verified"]
    assert valid["approvals"][0]["verified"]
    with db.session() as s:
        s.execute(text("UPDATE agent_versions SET system_prompt='Changed without hash' WHERE id=:id"), {"id": version["id"]})
    snapshot = client.get(PREFIX + "/snapshot").json()
    assert not snapshot["versions"][0]["integrity_valid"]
    assert not snapshot["versions"][0]["bench_eligible"]
    assert not snapshot["versions"][0]["governance_valid"]
    assert not snapshot["evaluations"][0]["verified"]
    assert not snapshot["approvals"][0]["verified"]
    before = len(runtime.requests)
    response = client.post(PREFIX + "/runs", json={
        "assignment_id": assignment["id"], "prompt": "Research safely",
        "idempotency_key": secrets.token_hex(16), "allow_remote_model": True,
    })
    assert response.status_code == 409 and len(runtime.requests) == before


def test_snapshot_marks_forged_bench_and_malformed_details_unverified(studio):
    client, db, runtime, app = studio
    bp, version = draft(client)
    client.post(PREFIX + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    with db.session() as s:
        s.execute(text("UPDATE bench_evaluations SET details_json='malformed'"))
    response = client.get(PREFIX + "/snapshot")
    assert response.status_code == 200
    assert not response.json()["evaluations"][0]["verified"]
    assert not response.json()["versions"][0]["bench_eligible"]
