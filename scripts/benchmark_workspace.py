"""Reproducible disposable API benchmark, with signed lifecycle evidence intact."""
import argparse
import json
import platform
import statistics
import secrets
from contextlib import contextmanager
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from database.connection import DatabaseManager, create_db_engine
from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT, create_app, migrate
from tests.integration.test_studio_api import ORIGIN, PREFIX, draft, promoted
from tests.studio_runtime import IsolatedTestRuntime
from tests.workspace_dataset import seed_workspace_dataset


def measure(client, path, samples):
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        response = client.get(path)
        assert response.status_code == 200, response.text
        timings.append((time.perf_counter() - started) * 1000)
    ordered = sorted(timings)
    return {"samples": samples, "p50_ms": round(statistics.median(timings), 2),
        "p95_ms": round(ordered[min(len(ordered)-1, int(len(ordered)*0.95))], 2), "max_ms": round(max(timings), 2)}


@contextmanager
def disposable_database():
    import os
    with tempfile.TemporaryDirectory(prefix="aryn-workspace-benchmark-") as directory:
        os.environ["ARYN_ENV"] = "development"
        os.environ["ARYN_IDENTITY_SECRET"] = secrets.token_hex(32)
        os.environ["ARYN_EVIDENCE_SECRET"] = secrets.token_hex(32)
        os.environ["ARYN_HISTORY_COMMITMENT_PATH"] = str(Path(directory) / "commitments.sqlite3")
        db = DatabaseManager(create_db_engine(f"sqlite:///{Path(directory).as_posix()}/workspace.sqlite3"))
        try:
            migrate(db.engine)
            yield db
        finally:
            db.engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".local/studio-evidence/workspace-performance.json")
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    import os
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    result = {"source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_modified": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "environment": {"platform": platform.platform(), "python": platform.python_version(), "processor": platform.processor(), "database": "SQLite disposable", "transport": "FastAPI TestClient; no live provider"},
        "thresholds_ms": {"summary_p95": 2000, "interactive_navigation_p95": 3000}, "datasets": {}}
    for size in ("small", "large"):
        with disposable_database() as db:
            app = create_app(db, IsolatedTestRuntime(), testing=True)
            ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
            with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
                token = client.post("/api/session", json={}, headers={"Origin": ORIGIN}).json()["csrf"]
                client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": token})
                bp, version = draft(client)
                assignment = promoted(client, bp, version)
                response = client.post(PREFIX + "/runs", json={"assignment_id": assignment["id"], "prompt": "Review disposable evidence safely.", "idempotency_key": "workspace-performance-run", "allow_remote_model": True})
                assert response.status_code == 200, response.text
                counts = seed_workspace_dataset(db, ctx, size)
                summary = client.get(PREFIX + "/summary").json()
                assert summary["latest_runs"][0]["verified"] and all(item["verified"] for item in summary["latest_audits"])
                result["datasets"][size] = {"fixture": counts, "real_lifecycle": "1 blueprint/version, 4 Bench scenarios, approval, publication, assignment, captured manual run",
                    "summary": measure(client, PREFIX + "/summary", args.samples),
                    "snapshot": measure(client, PREFIX + "/snapshot", args.samples),
                    "project_list": measure(client, PREFIX + "/resources/projects", args.samples)}
                assert result["datasets"][size]["summary"]["p95_ms"] <= 2000
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
