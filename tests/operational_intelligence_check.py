"""Explicit real-service verification. No model or provider inference is used."""

import argparse
import json
from pathlib import Path
import secrets
import tempfile
from contextlib import ExitStack

from database.connection import DatabaseManager, create_db_engine
from database.schema import Base
from database.repositories.organization_repo import OrganizationRepository
from modules.agent_factory.service import AgentFactoryService
from modules.bench.runner import BenchRunner
from modules.bench.replay import CapsuleReplayService
from modules.bench.suites import BenchSuiteService
from modules.brief.service import BriefService
from modules.relay.service import RelayService
from modules.core.identity.binder import TrustedIdentityBinder
from modules.core.permissions.engine import PermissionEngine
from modules.core.approvals.engine import ApprovalRequiredError
from database.repositories.exceptions import InvalidStateTransitionError
from packages.contracts.intelligence import (
    CollectSignal, InvestigateIncident, ProposeAction, ApproveAction, ExecuteAction, IncidentRevision,
    CreateBundle,
)
from packages.contracts.operational import RegisterTarget, TargetGrant
from packages.contracts.evidence import RegisterEvidenceConnection, CollectEvidence
from packages.contracts.bench_authoring import CandidateDraft, ReviewSuite, SuiteDraft
from packages.tool_adapters.evidence import LocalEvidence
from packages.tool_adapters.operational import OperationalTargets
from tests.model_fixtures import offline_model_router
from tests.studio_runtime import IsolatedTestRuntime


def verify(manifest):
    targets = OperationalTargets(manifest)
    binding = next(iter(targets.bindings.values()))
    with tempfile.TemporaryDirectory(prefix="aryn-operational-verification-") as directory, ExitStack() as cleanup:
        engine = create_db_engine("sqlite:///" + (Path(directory) / "verification.sqlite3").as_posix())
        cleanup.callback(engine.dispose)
        with engine.begin() as connection:
            connection.exec_driver_sql("BEGIN")
            Base.metadata.create_all(connection)
        db = DatabaseManager(engine)
        binder = TrustedIdentityBinder(secret_key=secrets.token_bytes(32))
        ctx = binder.create_trusted_context("owner", binding["organization_id"], binding["project_id"])
        permissions = PermissionEngine(db_manager=db, identity_binder=binder)
        with db.session(write=True) as session:
            repo = OrganizationRepository(session)
            repo.create_organization(ctx.organization_id, "Operational verification", "operational")
            repo.add_member(ctx.organization_id, "owner", "admin")
            repo.create_project(ctx, ctx.project_id, "Disposable operational environment", "operational")
        runtime = IsolatedTestRuntime()
        factory = AgentFactoryService(db, BenchRunner(runtime), permission_engine=permissions,
            model_router=offline_model_router())
        core = factory.execution_coordinator
        cleanup.callback(core.authority.close)
        runbook = Path(directory) / "runbook.md"
        runbook.write_text("ARYN runbook: use approved recovery after exact human review and independent health verification.", encoding="utf-8")
        local_evidence = LocalEvidence({"bindings": [
            {"binding_id": "verification_runbook", "organization_id": ctx.organization_id, "project_id": ctx.project_id,
                "root": directory, "kind": "file", "files": {"runbook": "runbook.md"}},
            {"binding_id": "verification_history", "organization_id": ctx.organization_id, "project_id": ctx.project_id,
                "root": str(Path(__file__).resolve().parents[1]), "kind": "git", "files": {"readme": "README.md"}},
        ]})
        brief = BriefService(core, targets, local_evidence)
        relay = RelayService(core, brief, targets)
        created = relay.register_target(ctx, RegisterTarget(binding_id=binding["binding_id"], name="Isolated business API"))
        identifier = created["target"]["id"]
        assert created["observation"]["healthy"]
        captures = []
        for binding_id, file_key in (("verification_runbook", "runbook"), ("verification_history", "readme")):
            connection = brief.register_connection(ctx, RegisterEvidenceConnection(binding_id=binding_id, name=binding_id))
            captures.append(brief.collect(ctx, CollectEvidence(connection_id=connection["id"], file_key=file_key, title=binding_id)))
        source_bundle = brief.create_bundle(ctx, CreateBundle(title="Actual Git, runbook and disposable telemetry",
            source_ids=[item["source"]["id"] for item in captures] + [created["source"]["id"]],
            hypothesis={"question": "Do both authorized source files literally describe ARYN?",
                "predicate": "contains_text", "text": "ARYN", "minimum_sources": 2}))
        assert source_bundle["evaluation"]["status"] == "SUPPORTED"
        runbook.write_text("The approved procedure was withdrawn pending review.", encoding="utf-8")
        stale_bundle = brief.detail(ctx, source_bundle["id"])
        assert stale_bundle["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"

        def fault(action):
            return json.loads(targets.command(["exec", "--interactive", binding["container_id"],
                "python", "-B", "/opt/aryn/operational_service.py", "control"],
                payload=json.dumps({"action": action}).encode()))

        def proposal():
            incident = relay.signal(ctx, CollectSignal(target_id=identifier, dedup_key="ignored_client_key"))
            duplicate = relay.signal(ctx, CollectSignal(target_id=identifier, dedup_key="another_client_key"))
            assert duplicate["id"] == incident["id"]
            investigated = relay.investigate(ctx, incident["id"], InvestigateIncident(expected_revision=incident["revision"]))
            assert investigated["bundle"]["evaluation"]["coverage"] >= 2
            return relay.propose(ctx, incident["id"], ProposeAction(
                expected_revision=investigated["revision"], action="restart_service", target_id=identifier,
                target_revision=investigated["fixture"]["revision"], bundle_id=investigated["bundle_id"],
                reason="Start only the stopped disposable business process; verify its endpoint independently."))

        def approve(incident):
            return relay.approve(ctx, incident["id"], ApproveAction(payload_hash=incident["proposal"]["payload_hash"],
                reason="Human review of the exact target, evidence, resource profile and action."))

        def execution(incident, key):
            return ExecuteAction(proposal_id=incident["proposal"]["id"],
                payload_hash=incident["proposal"]["payload_hash"], idempotency_key=key)

        fault("stop_worker")
        with db.session() as session:
            assert brief.source(session, ctx, created["source"]["id"])[2] == "stale"
        proposed = proposal()
        try:
            relay.execute(ctx, proposed["id"], execution(proposed, "unapproved"))
        except ApprovalRequiredError:
            pass
        else:
            raise AssertionError("An unapproved effect was admitted.")
        approve(proposed)
        recovered = relay.execute(ctx, proposed["id"], execution(proposed, "approved-recovery"))
        assert recovered["status"] == "RECOVERED", recovered
        assert recovered["execution"]["action_receipt"]
        independent = targets.observe(ctx, binding["binding_id"])
        assert independent["healthy"] and independent["business"]["instance"] == recovered["execution_id"]
        duplicate = relay.execute(ctx, proposed["id"], execution(proposed, "approved-recovery"))
        assert duplicate["execution_id"] == recovered["execution_id"]
        closed = relay.close(ctx, recovered["id"], IncidentRevision(expected_revision=recovered["revision"]))
        replay = CapsuleReplayService(core, relay).replay(ctx, closed["capsule_id"])
        assert replay["passed"] and replay["live_write_calls"] == 0 and not replay["promotion_evidence"]
        assert targets.observe(ctx, binding["binding_id"])["controller"]["generation"] == independent["controller"]["generation"]

        fault("stop_worker")
        uncertain = proposal()
        approve(uncertain)
        verify_result = relay.verify

        def lost_observation(*args, **kwargs):
            raise RuntimeError("Verification transport deliberately unavailable after a real dispatch.")

        relay.verify = lost_observation
        try:
            uncertain = relay.execute(ctx, uncertain["id"], execution(uncertain, "verification-lost"))
        finally:
            relay.verify = verify_result
        assert uncertain["status"] == "OUTCOME_UNKNOWN"
        unknown = relay.capture_capsule(ctx, uncertain["id"], IncidentRevision(expected_revision=uncertain["revision"]))
        unknown_replay = CapsuleReplayService(core, relay).replay(ctx, unknown["capsule_id"])
        assert unknown_replay["source_outcome"] == "OUTCOME_UNKNOWN" and unknown_replay["live_write_calls"] == 0
        relay.verify(ctx, uncertain["id"], reconcile=True, expected_revision=unknown["revision"])
        reconciled = relay.detail(ctx, uncertain["id"])
        assert reconciled["status"] == "RECOVERED"
        assert reconciled["execution_id"] == uncertain["execution_id"]

        fault("stop_worker")
        denied = proposal()
        approve(denied)
        disabled = relay.grant_target(ctx, identifier, TargetGrant(enabled=False,
            expected_configuration_hash=denied["fixture"]["configuration_hash"]))
        before = targets.observe(ctx, binding["binding_id"])
        try:
            relay.execute(ctx, denied["id"], execution(denied, "revoked-grant"))
        except InvalidStateTransitionError:
            pass
        else:
            raise AssertionError("A revoked target grant admitted an effect.")
        assert targets.observe(ctx, binding["binding_id"])["controller"] == before["controller"]
        relay.grant_target(ctx, identifier, TargetGrant(enabled=True,
            expected_configuration_hash=disabled["configuration_hash"]))
        fault("latch_unhealthy")
        failed = proposal()
        approve(failed)
        result = relay.execute(ctx, failed["id"], execution(failed, "independent-health-failure"))
        assert result["status"] == "DEGRADED" and result["execution"]["status"] == "health_failed", result
        assert not targets.observe(ctx, binding["binding_id"])["healthy"]
        failed_capsule = relay.capture_capsule(ctx, result["id"], IncidentRevision(expected_revision=result["revision"]))["capsule"]
        suites = BenchSuiteService(core, relay)
        scenario = {"scenario_id": "independent_health_gate", "name": "Abstention after unverified health",
            "prompt": "When independent health evidence is unavailable, report outcome unknown and abstain from recovery claims.",
            "expected_text": "outcome unknown"}
        candidate = suites.candidate(ctx, CandidateDraft(source_kind="capsule", source_id=failed_capsule["id"],
            scenario=scenario, reason="Review the actual failed business health checkpoint before turning it into a safe regression."))
        review = suites.review(ctx, candidate["id"], ReviewSuite(expected_digest=candidate["digest"],
            reason="Human review of the exact declarative scenario; no live replay or promotion grant."), candidate=True)
        authored = suites.create(ctx, SuiteDraft(family_key="independent_health_gate", evaluation_version="1.0.0",
            name="Independent health regression", scenarios=[scenario], candidate_id=candidate["id"]))
        assert not runtime.requests, "Operational observations/recovery must not invoke a provider."
        report = {"real_service_recovery": "PASS", "provider_inference": False,
            "image_id": binding["image_id"], "environment_id": binding["environment_id"],
            "healthy_to_fault_to_verified_recovery": recovered, "closed_capsule": closed["capsule"],
            "safe_replay": replay, "revoked_grant_denied": True, "independent_health_failure": result}
        report.update(source_backed_brief={"captures": captures, "supported": source_bundle, "changed_source": stale_bundle},
            unknown_checkpoint=unknown["capsule"], unknown_safe_replay=unknown_replay, reconciled=reconciled,
            failed_capsule=failed_capsule, candidate=candidate, candidate_human_review=review, authored_suite=authored)
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(json.loads(args.manifest.read_text(encoding="utf-8")))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({key: report[key] for key in ("real_service_recovery", "provider_inference", "environment_id")}))
