"""Authenticated Brief, Relay and model-free Bench capsule routes."""

from fastapi import Query, Request, HTTPException
from fastapi.responses import Response
from modules.brief.service import BriefService
from modules.relay.service import RelayService
from modules.bench.replay import CapsuleReplayService
from modules.core.records import encoded
from database.schema import EvidenceSourceModel, DemoFixtureModel, RelayEventModel
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


def register_intelligence(app, coordinator, context):
    brief = BriefService(coordinator)
    relay = RelayService(coordinator, brief)
    replay = CapsuleReplayService(coordinator, relay)
    relay.recover()
    app.state.brief, app.state.relay, app.state.capsule_replay = brief, relay, replay
    prefix = "/api/projects/{project_id}"

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

    @app.post(prefix + "/brief/documents", status_code=201)
    def document(project_id: str, body: CreateDocument):
        return brief.document(context(project_id), body)

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
            return {"items": items, "next": cursor}

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
            pattern="^(run|artifact|workflow_run|incident|capsule|replay)$"
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
            return {"items": items, "next": cursor}

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
