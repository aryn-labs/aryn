"""Actual API/Core browser fixture; migrated disposable DB and isolated test inference only."""
import os
import json
import tempfile
from pathlib import Path
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import text
from database.connection import DatabaseManager, create_db_engine
from database.repositories.organization_repo import OrganizationRepository
from services.api.studio import create_app, migrate, DEV_ACTOR, DEV_ORG, DEV_PROJECT
from tests.studio_runtime import IsolatedTestRuntime
from tests.integration.test_studio_api import draft, promoted
from tests.integration.test_intelligence_recovery import demo_incident, investigated, proposed, approved, execution_body, post
from tests.operational_fixtures import OperationalProtocolDouble
from packages.tool_adapters.evidence import LocalEvidence
from packages.tool_adapters.operational import OperationalTargets


def main():
    os.environ["ARYN_ENV"] = "development"
    os.environ["ARYN_AUTH_MODE"] = "local-development"
    with tempfile.TemporaryDirectory(prefix="aryn-intelligence-browser-") as directory:
        engine = create_db_engine("sqlite:///" + (Path(directory) / "intelligence.sqlite3").as_posix())
        migrate(engine)
        db, runtime, origin = DatabaseManager(engine), IsolatedTestRuntime(), "http://127.0.0.1:8879"
        try:
            root = Path(directory)
            (root / "runbook.md").write_text("Runbook: approved recovery requires exact human approval and independent health verification.", encoding="utf-8")
            local_evidence = LocalEvidence({"bindings": [
                {"binding_id": "browser_runbooks", "organization_id": DEV_ORG, "project_id": DEV_PROJECT,
                    "root": str(root), "kind": "file", "files": {"runbook": "runbook.md"}},
                {"binding_id": "browser_source_history", "organization_id": DEV_ORG, "project_id": DEV_PROJECT,
                    "root": str(Path(__file__).resolve().parents[1]), "kind": "git", "files": {"readme": "README.md"}},
            ]})
            configured_target = os.getenv("ARYN_TEST_OPERATIONAL_MANIFEST")
            targets = OperationalTargets(json.loads(Path(configured_target).read_text(encoding="utf-8"))) if configured_target else OperationalProtocolDouble()
            app = create_app(db, runtime, origin=origin, testing=True,
                operational_targets=targets, local_evidence=local_evidence)
            ctx = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
            with db.session(write=True) as session:
                repo = OrganizationRepository(session)
                repo.create_project(ctx, "proj_intelligence_empty", "Proyek Intelijen Kosong", "intelligence-empty")
                repo.add_project_member("proj_intelligence_empty", DEV_ACTOR)
            evidence = {"test_fixture": True, "runtime": "IsolatedTestRuntime", "live_provider": False,
                "operational_transport": "actual isolated Docker service" if configured_target else "OperationalProtocolDouble", "file_evidence": "actual temporary file",
                "git_evidence": "actual read-only repository blob", "project": DEV_PROJECT}
            evidence["git_revision"] = local_evidence.revision(ctx, "browser_source_history")
            with TestClient(app, base_url=origin, client=("127.0.0.1", 50100)) as client:
                session = client.post("/api/session", json={}, headers={"Origin": origin}).json()
                client.headers.update({"Origin": origin, "X-CSRF-Token": session["csrf"]})
                bp, version = draft(client, "intelligence-evaluation")
                assignment = promoted(client, bp, version)
                run = post(client, '/runs', {'assignment_id': assignment['id'], 'prompt': 'Isolated cross-module evidence', 'idempotency_key': 'intelligence-browser-run', 'allow_remote_model': True})
                evidence['run'] = run['run_id']
                evidence["assignment"] = assignment["id"]
                run_source = post(client, '/brief/sources', {'title': 'Governed run snapshot', 'source_ref': {'kind': 'run', 'id': evidence['run']}})
                evidence['run_bundle'] = post(client, '/brief', {'title': 'Run completion evidence', 'source_ids': [run_source['id']], 'hypothesis': {'question': 'Did this exact governed run complete?', 'predicate': 'run_completed'}})['id']
                candidate = post(client, f"/blueprints/{bp['id']}/versions", {"version_number": "1.1.0", "system_prompt": version["system_prompt"], "model": "test/model-a", "max_tokens": 512})
                result = post(client, f"/versions/{candidate['id']}/bench", {"allow_remote_model": True})
                evidence["evaluation"] = result["evaluation_id"]
                evidence["blueprint"] = bp["id"]
                evidence["version"] = candidate["id"]
                failed = post(client, f"/blueprints/{bp['id']}/versions", {"version_number": "1.2.0", "system_prompt": version["system_prompt"], "model": "test/model-a", "max_tokens": 512})
                runtime.fail = True
                evidence["failed_evaluation"] = post(client, f"/versions/{failed['id']}/bench", {"allow_remote_model": True})["evaluation_id"]
                runtime.fail = False
                # Negative evidence fixture: corrupt a real evaluation only in this disposable database.
                legacy_bp, legacy = draft(client, "intelligence-corruption-negative")
                legacy_result = post(client, f"/versions/{legacy['id']}/bench", {"allow_remote_model": True})
                evidence["unverified_evaluation"] = legacy_result["evaluation_id"]
                with db.session(write=True) as storage:
                    storage.execute(text("UPDATE bench_evaluations SET provenance_json='{}' WHERE id=:id"), {"id": legacy_result["evaluation_id"]})
                source = post(client, "/brief/documents", {"title": "Dokumen Pengujian Terisolasi", "text": "Literal audit-pass. This is a sanitized test document, not external factual proof."})["source"]
                for predicate, literal in (("contains_text", "audit-pass"), ("contains_text", "missing-contract"), ("run_completed", "")):
                    bundle = post(client, "/brief", {"title": "Isolated " + (literal or predicate), "source_ids": [source["id"]], "hypothesis": {"question": "Does the captured origin support this typed observation?", "predicate": predicate, "text": literal}})
                    if literal == "audit-pass":
                        evidence["bundle"] = bundle["id"]
                _, _, incident = demo_incident(client, key="browser-open")
                evidence["incident"] = incident["id"]
                for label, fault in (("closed", False), ("degraded", True), ("unknown", False)):
                    _, _, incident = demo_incident(client, blocking_fault=fault, key="browser-" + label)
                    incident = proposed(client, investigated(client, incident))
                    approved(client, incident)
                    verify = app.state.relay.verify
                    if label == "unknown":
                        def unavailable(*args, **kwargs):
                            raise RuntimeError("Isolated lost verification checkpoint")
                        app.state.relay.verify = unavailable
                    try:
                        incident = post(client, f"/relay/{incident['id']}/execute", execution_body(incident, "browser-" + label))
                    finally:
                        app.state.relay.verify = verify
                    if label == "closed":
                        incident = post(client, f"/relay/{incident['id']}/close", {"expected_revision": incident["revision"]})
                        evidence["capsule"] = incident["capsule_id"]
                        evidence["replay"] = post(client, f"/bench/capsules/{incident['capsule_id']}/replay")["id"]
                    evidence[label + "_incident"] = incident["id"]
                binding = next(iter(targets.bindings.values()))
                target = post(client, "/relay/targets", {"binding_id": binding["binding_id"], "name": "Browser operational service"})["target"]
                if configured_target:
                    targets.command(["exec", "--interactive", binding["container_id"], "python", "-B",
                        "/opt/aryn/operational_service.py", "control"], payload=b'{"action":"stop_worker"}')
                else:
                    targets.fault()
                incident = post(client, "/relay/signals", {"target_id": target["id"], "dedup_key": "browser_service_fault"})
                evidence["operational_incident"] = incident["id"]
                evidence["operational_target"] = target["id"]
                evidence["inference_calls_before_browser"] = len(runtime.requests)
            output = Path(".local/intelligence-evidence")
            output.mkdir(parents=True, exist_ok=True)
            (output / "core-records.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            uvicorn.run(app, host="127.0.0.1", port=8879, access_log=False)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
