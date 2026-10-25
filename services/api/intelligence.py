"""Authenticated Brief, Relay and model-free Bench capsule routes."""

from fastapi import Query, Request, HTTPException
from fastapi.responses import Response
from modules.brief.service import BriefService
from modules.relay.service import RelayService
from modules.bench.replay import CapsuleReplayService
from modules.bench.workspace import BenchWorkspace
from modules.bench.suites import BenchSuiteService
from modules.core.records import encoded, digest
from database.schema import EvidenceSourceModel, DemoFixtureModel, RelayEventModel, EvidenceLinkModel
from packages.contracts.intelligence import (
    CreateDocument,
    IngestReference,
    CreateBundle,
    CreateFixture,
    ChangeFixture,
    CollectSignal,
    InvestigateIncident,
    ProposeAction,
    ApproveAction,
    ExecuteAction,
    IncidentRevision,
    ReplayCapsule,
)


def register_intelligence(app, coordinator, context, operational_targets=None, local_evidence=None):
    brief = BriefService(coordinator, operational_targets, local_evidence)
    relay = RelayService(coordinator, brief, operational_targets)
    replay = CapsuleReplayService(coordinator, relay)
    bench = BenchWorkspace(coordinator)
    suite_service = BenchSuiteService(coordinator, relay)
    relay.recover()
    app.state.brief, app.state.relay, app.state.capsule_replay = brief, relay, replay
    prefix = "/api/projects/{project_id}"

    from packages.contracts.operational import RegisterTarget, TargetGrant, service_target

    @app.get(prefix + "/relay/target-bindings")
    def target_bindings(project_id: str, request: Request):
        queries(request, set())
        ctx = context(project_id)
        with brief.db.session() as session:
            brief.authorize(session, ctx, "tool:register")
            return {"organization_id": ctx.organization_id, "project_id": ctx.project_id,
                "configured": operational_targets is not None, "items": [
                {"binding_id": item["binding_id"], "environment_id": item["environment_id"],
                    "binding_hash": digest(item),
                    "profile": item["profile"], "allowed_actions": ["restart_service"]}
                for item in operational_targets.bindings.values()
                if (item["organization_id"], item["project_id"]) == (ctx.organization_id, ctx.project_id)
            ] if operational_targets else []}

    @app.get(prefix + "/relay/targets")
    def targets(project_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        ctx = context(project_id)
        with brief.db.session() as session:
            items, cursor = brief.page(session, ctx, DemoFixtureModel, after, limit)
            return {"items": [item for item in items if service_target(item)], "next": cursor}

    @app.post(prefix + "/relay/targets", status_code=201)
    def register_target(project_id: str, body: RegisterTarget):
        return relay.register_target(context(project_id), body)

    @app.post(prefix + "/relay/targets/{target_id}/observe")
    def observe_target(project_id: str, target_id: str):
        return relay.observe_target(context(project_id), target_id)

    @app.post(prefix + "/relay/targets/{target_id}/grant")
    def grant_target(project_id: str, target_id: str, body: TargetGrant):
        return relay.grant_target(context(project_id), target_id, body)

    @app.post(prefix + "/relay/{incident_id}/cancel")
    def cancel_incident(project_id: str, incident_id: str, body: IncidentRevision):
        return relay.cancel(context(project_id), incident_id, body)

    @app.post(prefix + "/relay/{incident_id}/capsule")
    def capture_incident_capsule(project_id: str, incident_id: str, body: IncidentRevision):
        return relay.capture_capsule(context(project_id), incident_id, body)

    @app.get(prefix + "/relay/capsules")
    def capsules(project_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        from database.schema import IncidentCapsuleModel, RelayCapsuleModel
        queries(request, {"after", "limit"})
        with relay.db.session() as session:
            items, cursor = relay.page_any(session, (IncidentCapsuleModel, RelayCapsuleModel), context(project_id), after, limit)
            return {"items": items, "next": cursor}

    def queries(request, allowed):
        if any(
            key not in allowed or len(request.query_params.getlist(key)) != 1
            for key in request.query_params
        ):
            raise HTTPException(422, "Unknown or duplicate query.")

    def attachment(payload, identifier):
        return Response(
            encoded(payload),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="aryn-{identifier}.json"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    @app.get(prefix + "/intelligence/context")
    def intelligence_context(project_id: str):
        ctx = context(project_id)
        with brief.db.session() as session:
            brief.authorize(session, ctx)
            return {"organization_id": ctx.organization_id, "project_id": ctx.project_id,
                    "permissions": {action: brief.permissions.evaluate(action, ctx, ctx.organization_id,
                        ctx.project_id, session=session).allowed for action in
                        ("version:create", "version:approve", "run:create", "run:cancel", "tool:register", "bench:accept_baseline")}}

    @app.get(prefix + "/bench/suites")
    def bench_suites(project_id: str):
        return bench.suites(context(project_id))

    from packages.contracts.bench_authoring import SuiteDraft, ReviewSuite, CandidateDraft

    @app.get(prefix + "/bench/suite-versions")
    def suite_versions(project_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        return suite_service.inventory(context(project_id), after=after, limit=limit)

    @app.post(prefix + "/bench/suite-versions", status_code=201)
    def create_suite_version(project_id: str, body: SuiteDraft):
        return suite_service.create(context(project_id), body)

    @app.post(prefix + "/bench/suite-versions/{suite_id}/review")
    def review_suite_version(project_id: str, suite_id: str, body: ReviewSuite):
        return suite_service.review(context(project_id), suite_id, body)

    @app.get(prefix + "/bench/scenario-candidates")
    def candidates(project_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        return suite_service.inventory(context(project_id), candidates=True, after=after, limit=limit)

    @app.post(prefix + "/bench/scenario-candidates", status_code=201)
    def create_candidate(project_id: str, body: CandidateDraft):
        return suite_service.candidate(context(project_id), body)

    @app.post(prefix + "/bench/scenario-candidates/{candidate_id}/review")
    def review_candidate(project_id: str, candidate_id: str, body: ReviewSuite):
        return suite_service.review(context(project_id), candidate_id, body, candidate=True)

    @app.get(prefix + "/bench/evaluations/{evaluation_id}/regression/download")
    def download_regression(project_id: str, evaluation_id: str):
        ctx = context(project_id)
        report = bench.detail(ctx, evaluation_id)
        if not report["verified"] or report["regression"] is None:
            raise HTTPException(409, "Verified evaluation and regression evidence are required.")
        from modules.core.records import now
        payload = {"organization_id": ctx.organization_id, "project_id": ctx.project_id,
            "exported_by": ctx.actor.actor_id, "exported_at": now(), "evaluation": report}
        return attachment({"payload": payload, "attestation": brief.db.evidence_signer.sign(
            "bench_regression_export", payload)}, evaluation_id)

    @app.get(prefix + "/bench/evaluations")
    def evaluations(project_id: str, request: Request, after: str = Query("", max_length=64),
                    limit: int = Query(25, ge=1, le=100), q: str = Query("", max_length=100),
                    blueprint_id: str = Query("", pattern="^[A-Za-z0-9_-]{0,64}$"),
                    version_id: str = Query("", pattern="^[A-Za-z0-9_-]{0,64}$"),
                    suite_id: str = Query("", pattern="^[A-Za-z0-9_.-]{0,100}$"),
                    status: str = Query("", pattern="^(|passed|failed)$")):
        queries(request, {"after", "limit", "q", "blueprint_id", "version_id", "suite_id", "status"})
        return bench.inventory(context(project_id), after, limit, q, blueprint_id, version_id, suite_id, status)

    @app.get(prefix + "/bench/evaluations/{evaluation_id}")
    def evaluation_detail(project_id: str, evaluation_id: str):
        return bench.detail(context(project_id), evaluation_id)

    @app.post(prefix + "/brief/documents", status_code=201)
    def document(project_id: str, body: CreateDocument):
        return brief.document(context(project_id), body)

    from packages.contracts.evidence import RegisterEvidenceConnection, EvidenceConnectionGrant, CollectEvidence, InterpretBundle
    from database.schema import EvidenceConnectionModel, BriefInterpretationModel

    @app.get(prefix + "/brief/connection-bindings")
    def evidence_bindings(project_id: str, request: Request):
        queries(request, set())
        ctx = context(project_id)
        with brief.db.session() as session:
            brief.authorize(session, ctx, "tool:register")
            return {"organization_id": ctx.organization_id, "project_id": ctx.project_id,
                "configured": local_evidence is not None, "items": [
                {"binding_id": item["binding_id"], "binding_hash": digest(item), "kind": item["kind"],
                    "file_keys": list(item["files"])} for item in local_evidence.bindings.values()
                if (item["organization_id"], item["project_id"]) == (ctx.organization_id, ctx.project_id)
            ] if local_evidence else []}

    @app.get(prefix + "/brief/connections")
    def connections(project_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        with brief.db.session() as session:
            items, cursor = brief.page(session, context(project_id), EvidenceConnectionModel, after, limit)
            return {"items": items, "next": cursor}

    @app.post(prefix + "/brief/connections", status_code=201)
    def register_evidence_connection(project_id: str, body: RegisterEvidenceConnection):
        return brief.register_connection(context(project_id), body)

    @app.post(prefix + "/brief/connections/{connection_id}/grant")
    def grant_evidence_connection(project_id: str, connection_id: str, body: EvidenceConnectionGrant):
        return brief.grant_connection(context(project_id), connection_id, body)

    @app.post(prefix + "/brief/collect", status_code=201)
    def collect_evidence(project_id: str, body: CollectEvidence):
        return brief.collect(context(project_id), body)

    @app.post(prefix + "/brief/{bundle_id}/interpret", status_code=201)
    async def interpret_bundle(project_id: str, bundle_id: str, body: InterpretBundle):
        return await brief.interpret(context(project_id), bundle_id, body)

    @app.get(prefix + "/brief/interpretation-agents")
    def interpretation_agents(project_id: str, request: Request):
        queries(request, set())
        from database.schema import AgentAssignmentModel
        from database.repositories.agent_repo import AgentRepository
        from packages.contracts.agent import AgentVersion
        ctx = context(project_id)
        with brief.db.session() as session:
            brief.authorize(session, ctx)
            items = []
            for assignment in session.query(AgentAssignmentModel).filter_by(organization_id=ctx.organization_id,
                    project_id=ctx.project_id, status="active").order_by(AgentAssignmentModel.id).limit(100).all():
                version = AgentVersion.from_stored(AgentRepository(session).get_version(ctx, assignment.version_id))
                if version.status.value == "published" and not version.tool_grants:
                    items.append({"assignment_id": assignment.id, "role_name": assignment.role_name,
                        "version_id": version.id, "model": version.model,
                        "max_tokens": version.budget_policy.max_tokens_per_run,
                        "max_cost_usd": version.budget_policy.max_cost_usd})
            return {"organization_id": ctx.organization_id, "project_id": ctx.project_id, "items": items}

    @app.get(prefix + "/brief/{bundle_id}/interpretations")
    def interpretations(project_id: str, bundle_id: str, request: Request, after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        ctx = context(project_id)
        with brief.db.session() as session:
            brief.authorize(session, ctx)
            brief.bundle_detail_in_session(session, ctx, bundle_id)
            items, cursor = brief.page(session, ctx, BriefInterpretationModel, after, limit, bundle_id=bundle_id)
            return {"items": items, "next": cursor}

    @app.post(prefix + "/brief/sources", status_code=201)
    def ingest(project_id: str, body: IngestReference):
        return brief.ingest(context(project_id), body)

    @app.get(prefix + "/brief/sources")
    def sources(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        with brief.db.session() as session:
            items, cursor = brief.page(
                session, context(project_id), EvidenceSourceModel, after, limit
            )
            from modules.core.history import HistoryUnverifiedError
            from database.repositories.exceptions import EntityNotFoundError
            ctx = context(project_id)
            enriched = []
            for item in items:
                try:
                    _, _, freshness = brief.source(session, ctx, item["id"])
                    integrity = "VERIFIED"
                except (HistoryUnverifiedError, EntityNotFoundError, ValueError, TypeError, KeyError):
                    integrity, freshness = "UNVERIFIED", "unavailable"
                enriched.append({**item, "integrity": integrity, "freshness": freshness})
            brief.authorize(session, ctx)
            return {"items": enriched, "next": cursor}

    @app.get(prefix + "/brief/sources/{source_id}")
    def source_detail(project_id: str, source_id: str):
        with brief.db.session() as session:
            ctx = context(project_id)
            source, content, freshness = brief.source(session, ctx, source_id)
            brief.authorize(session, ctx)
            return {
                **source,
                "integrity": "VERIFIED",
                "freshness": freshness,
                "content": content,
            }

    @app.get(prefix + "/brief")
    def bundles(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
        q: str = Query("", max_length=100),
        status: str = Query(
            "", pattern="^(|SUPPORTED|CONFLICTING|INSUFFICIENT_EVIDENCE|NOT_FOUND)$"
        ),
        workflow_run_id: str | None = Query(None, max_length=64),
    ):
        queries(request, {"after", "limit", "q", "status", "workflow_run_id"})
        return brief.inventory(
            context(project_id), after, limit, q, status, workflow_run_id
        )

    @app.get(prefix + "/brief-links")
    def evidence_links(
        project_id: str,
        request: Request,
        kind: str = Query(
            pattern="^(run|artifact|workflow_run|evaluation|incident|capsule|replay)$"
        ),
        id: str = Query(min_length=1, max_length=64),
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"kind", "id", "after", "limit"})
        return brief.related(context(project_id), kind, id, after, limit)

    @app.post(prefix + "/brief", status_code=201)
    def create_bundle(project_id: str, body: CreateBundle):
        return brief.create_bundle(context(project_id), body)

    @app.get(prefix + "/brief/{bundle_id}")
    def bundle(project_id: str, bundle_id: str):
        return brief.detail(context(project_id), bundle_id)

    @app.get(prefix + "/brief/{bundle_id}/download")
    def bundle_download(project_id: str, bundle_id: str):
        return attachment(brief.detail(context(project_id), bundle_id), bundle_id)

    @app.get(prefix + "/brief/{bundle_id}/links")
    def bundle_links(project_id: str, bundle_id: str, request: Request,
                     after: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=100)):
        queries(request, {"after", "limit"})
        ctx = context(project_id)
        brief.detail(ctx, bundle_id)
        with brief.db.session() as session:
            items, cursor = brief.page(session, ctx, EvidenceLinkModel, after, limit, bundle_id=bundle_id)
            return {"items": items, "next": cursor}

    @app.get(prefix + "/relay/demo-fixtures")
    def fixtures(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        with relay.db.session() as session:
            items, cursor = relay.page(
                session, context(project_id), DemoFixtureModel, after, limit
            )
            return {"items": [item for item in items if not service_target(item)], "next": cursor}

    @app.post(prefix + "/relay/demo-fixtures", status_code=201)
    def create_fixture(project_id: str, body: CreateFixture):
        return relay.create_fixture(context(project_id), body)

    @app.post(prefix + "/relay/demo-fixtures/{target_id}")
    def change_fixture(project_id: str, target_id: str, body: ChangeFixture):
        return relay.change_fixture(context(project_id), target_id, body)

    @app.post(prefix + "/relay/signals", status_code=201)
    def signal(project_id: str, body: CollectSignal):
        return relay.signal(context(project_id), body)

    @app.get(prefix + "/relay/capsules/{capsule_id}")
    def capsule(project_id: str, capsule_id: str):
        return relay.capsule(context(project_id), capsule_id)

    @app.get(prefix + "/relay/capsules/{capsule_id}/download")
    def capsule_download(project_id: str, capsule_id: str):
        return attachment(relay.capsule(context(project_id), capsule_id), capsule_id)

    @app.get(prefix + "/relay")
    def incidents(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
        q: str = Query("", max_length=100),
        status: str = Query(
            "",
            pattern="^(|OPEN|INVESTIGATING|PROPOSED|EXECUTING|DEGRADED|RECOVERED|CLOSED|OUTCOME_UNKNOWN)$",
        ),
    ):
        queries(request, {"after", "limit", "q", "status"})
        return relay.inventory(context(project_id), after, limit, q, status)

    @app.get(prefix + "/relay/{incident_id}")
    def incident(project_id: str, incident_id: str):
        return relay.detail(context(project_id), incident_id)

    @app.get(prefix + "/relay/{incident_id}/timeline")
    def timeline(
        project_id: str,
        incident_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        with relay.db.session() as session:
            ctx = context(project_id)
            relay.detail_in_session(session, ctx, incident_id)
            items, cursor = relay.page(
                session, ctx, RelayEventModel, after, limit, incident_id=incident_id
            )
            return {"items": items, "next": cursor}

    @app.post(prefix + "/relay/{incident_id}/investigate")
    def investigate(project_id: str, incident_id: str, body: InvestigateIncident):
        return relay.investigate(context(project_id), incident_id, body)

    @app.post(prefix + "/relay/{incident_id}/proposals")
    def proposal(project_id: str, incident_id: str, body: ProposeAction):
        return relay.propose(context(project_id), incident_id, body)

    @app.post(prefix + "/relay/{incident_id}/approve")
    def approve(project_id: str, incident_id: str, body: ApproveAction):
        return relay.approve(context(project_id), incident_id, body)

    @app.post(prefix + "/relay/{incident_id}/execute")
    def execute(project_id: str, incident_id: str, body: ExecuteAction):
        return relay.execute(context(project_id), incident_id, body)

    @app.post(prefix + "/relay/{incident_id}/close")
    def close(project_id: str, incident_id: str, body: IncidentRevision):
        return relay.close(context(project_id), incident_id, body)

    @app.post(prefix + "/relay/{incident_id}/reconcile")
    def reconcile(project_id: str, incident_id: str, body: IncidentRevision):
        ctx = context(project_id)
        relay.verify(
            ctx, incident_id, reconcile=True, expected_revision=body.expected_revision
        )
        return relay.detail(ctx, incident_id)

    @app.post(prefix + "/bench/capsules/{capsule_id}/replay", status_code=201)
    def capsule_replay(project_id: str, capsule_id: str, body: ReplayCapsule):
        return replay.replay(context(project_id), capsule_id)

    @app.get(prefix + "/bench/replays")
    def replays(
        project_id: str,
        request: Request,
        after: str = Query("", max_length=64),
        limit: int = Query(25, ge=1, le=100),
    ):
        queries(request, {"after", "limit"})
        return replay.inventory(context(project_id), after, limit)

    @app.get(prefix + "/bench/replays/{replay_id}")
    def replay_detail(project_id: str, replay_id: str):
        return replay.detail(context(project_id), replay_id)
