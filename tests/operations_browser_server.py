"""Rendered Runs/Automations over migrated disposable storage and actual Core, isolated inference."""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import uvicorn
from fastapi.testclient import TestClient
from database.connection import DatabaseManager, create_db_engine
from packages.contracts.projects import ProjectInput
from packages.contracts.runtime import RunStatus
from services.api.studio import create_app, migrate, DEV_ACTOR, DEV_ORG
from tests.studio_runtime import IsolatedTestRuntime
from tests.integration.test_studio_api import draft, promoted, PREFIX


def main():
    os.environ["ARYN_ENV"] = "development"
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    with tempfile.TemporaryDirectory(prefix="aryn-operations-browser-") as directory:
        engine = create_db_engine(
            "sqlite:///" + (Path(directory) / "operations.sqlite3").as_posix()
        )
        migrate(engine)
        try:
            runtime, origin = IsolatedTestRuntime(), "http://127.0.0.1:8878"
            app = create_app(
                DatabaseManager(engine), runtime, origin=origin, testing=True
            )
            ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, "")
            app.state.projects.save(
                ctx,
                ProjectInput(
                    name="Proyek Operasi Kosong",
                    description="Disposable browser verification",
                    idempotency_key="operations-project-seed",
                ),
            )
            with TestClient(
                app, base_url=origin, client=("127.0.0.1", 50000)
            ) as client:
                session = client.post(
                    "/api/session", json={}, headers={"Origin": origin}
                ).json()
                client.headers.update(
                    {"Origin": origin, "X-CSRF-Token": session["csrf"]}
                )
                blueprint, version = draft(client, "operations-agent")
                assignment = promoted(
                    client, blueprint, version, role_name="Agen Operasi Terisolasi"
                )
                for suffix, status in (
                    ("completed", RunStatus.COMPLETED),
                    ("unknown", RunStatus.OUTCOME_UNKNOWN),
                ):
                    runtime.status = status
                    response = client.post(
                        PREFIX + "/runs",
                        json={
                            "assignment_id": assignment["id"],
                            "prompt": "Isolated operations " + suffix,
                            "idempotency_key": "operations-" + suffix,
                            "allow_remote_model": True,
                        },
                    )
                    assert response.status_code == 200, response.status_code
                runtime.status = RunStatus.COMPLETED

                nodes = [
                    dict(id="start", label="Start", kind="start"),
                    dict(
                        id="agent",
                        label="Agen Terisolasi",
                        kind="agent",
                        assignment_id=assignment["id"],
                        agent_version_id=version["id"],
                    ),
                    dict(id="review", label="Human Review", kind="review"),
                    dict(id="end", label="End", kind="end"),
                ]
                graph = dict(
                    nodes=nodes,
                    edges=[
                        dict(id="edge_" + str(i), source=a["id"], target=b["id"])
                        for i, (a, b) in enumerate(zip(nodes, nodes[1:], strict=False))
                    ],
                )
                definition = client.post(
                    PREFIX + "/workflows",
                    json=dict(
                        name="Workflow Observasi Terisolasi",
                        graph=graph,
                        positions=[],
                        expected_revision=0,
                    ),
                ).json()
                frozen = client.post(
                    PREFIX + "/workflows/" + definition["id"] + "/versions",
                    json=dict(expected_revision=1),
                ).json()
                run = client.post(
                    PREFIX + "/workflows/" + definition["id"] + "/runs",
                    json=dict(
                        version_id=frozen["id"],
                        input="Actual isolated checkpoint evidence",
                        idempotency_key="operations-workflow",
                        allow_remote_model=True,
                    ),
                )
                assert (
                    run.status_code == 200 and run.json()["status"] == "waiting_review"
                )
                configuration = dict(
                    title="Otomatisasi Observasi",
                    target=dict(
                        kind="agent",
                        id=assignment["id"],
                        version_id=version["id"],
                        payload_hash=version["payload_hash"],
                        activation_id=assignment["current_transition_id"],
                    ),
                    input="Fixed isolated automation input",
                    allow_remote_model=True,
                    schedule=dict(
                        kind="daily",
                        timezone="Asia/Jakarta",
                        start_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )
                automation = client.post(
                    PREFIX + "/automations", json=configuration
                ).json()
                automation_root = PREFIX + "/automations/" + automation["id"]
                assert (
                    client.post(
                        automation_root + "/approve",
                        json=dict(
                            expected_revision=1,
                            payload_hash=automation["payload_hash"],
                            reason="Isolated explicit human approval",
                        ),
                    ).status_code
                    == 200
                )
                assert (
                    client.post(
                        automation_root + "/state",
                        json=dict(expected_revision=1, enabled=True),
                    ).status_code
                    == 200
                )
                client.post(
                    automation_root + "/run",
                    json=dict(
                        expected_revision=1, idempotency_key="operations-automation"
                    ),
                )
                runtime.status = RunStatus.OUTCOME_UNKNOWN
                unknown = client.post(
                    automation_root + "/run",
                    json=dict(
                        expected_revision=1,
                        idempotency_key="operations-automation-unknown",
                    ),
                )
                assert (
                    unknown.status_code == 200
                    and unknown.json()["status"] == "outcome_unknown"
                )
                runtime.status = RunStatus.COMPLETED

                # Safe evidence projection: actual Core/checkpoint identities,
                # never prompts, credential material or raw signed envelopes.
                inspection = client.get(PREFIX + "/executions").json()
                evidence = {
                    "test_fixture": True,
                    "runtime": "IsolatedTestRuntime",
                    "organization_id": inspection["organization_id"],
                    "project_id": inspection["project_id"],
                    "items": [],
                }
                for item in inspection["items"]:
                    observed = client.get(
                        PREFIX + "/executions/" + item["kind"] + "/" + item["id"]
                    ).json()
                    value = {
                        key: observed[key]
                        for key in (
                            "id",
                            "kind",
                            "status",
                            "source",
                            "verified",
                            "references",
                        )
                    }
                    if observed["workflow_run"]:
                        value["tasks"] = [
                            {
                                key: task[key]
                                for key in ("node_id", "status", "core_run_id")
                            }
                            for task in observed["workflow_run"]["tasks"]
                        ]
                        value["traversed_edges"] = observed["workflow_run"][
                            "traversed_edges"
                        ]
                    evidence["items"].append(value)
                evidence_directory = Path(".local/runs-automations-evidence")
                evidence_directory.mkdir(parents=True, exist_ok=True)
                (evidence_directory / "core-checkpoints.json").write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            @app.post("/__test__/tick")
            async def tick():
                return await app.state.automations.tick()

            uvicorn.run(app, host="127.0.0.1", port=8878, access_log=False)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
