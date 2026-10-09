"""Evidence snapshots rechecked against actual authorized internal/demo sources."""

import datetime
import hashlib
import json
from html.parser import HTMLParser

from database.schema import (
    EvidenceDocumentModel as DocumentRow,
    EvidenceSourceModel as SourceRow,
    EvidenceBundleModel as BundleRow,
    DemoObservationModel as ObservationRow,
    EvidenceLinkModel as LinkRow,
    WorkflowRunModel,
)
from database.repositories.run_state_repo import RunStateRepository
from database.repositories.exceptions import EntityNotFoundError
from modules.core.records import SignedRecords, encoded, digest, now
from modules.core.history import HistoryUnverifiedError
from modules.core.workflows.executor import WorkflowExecutor
from packages.contracts.intelligence import (
    EvidenceDocument,
    EvidenceSource,
    EvidenceBundle,
    EvidenceItem,
    SourceReference,
    EvidenceLink,
)


def bytes_digest(data):
    return hashlib.sha256(data).hexdigest()


class PlainDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


class BriefService(SignedRecords):
    def __init__(self, core):
        super().__init__(core)
        self.workflows = WorkflowExecutor(core)

    def origin(self, session, ctx, reference):
        reference = SourceReference.model_validate(reference)
        kind, identifier = reference.kind, reference.id
        if kind == "document":
            _, record = self.get(session, DocumentRow, ctx, identifier)
            if record["digest"] != bytes_digest(record["text"].encode()):
                raise HistoryUnverifiedError("Document digest differs.")
            return (
                {
                    "text": record["text"],
                    "demo": True,
                    "sanitized": record["sanitized"],
                },
                record["created_at"],
                "user_document",
            )
        if kind == "demo_observation":
            _, record = self.get(session, ObservationRow, ctx, identifier)
            if record["healthy"] != (
                record["running"] and not record["blocking_fault"]
            ):
                raise HistoryUnverifiedError("Demo health observation differs.")
            return (
                {
                    key: record[key]
                    for key in (
                        "target_id",
                        "target_revision",
                        "running",
                        "blocking_fault",
                        "healthy",
                        "disposable",
                    )
                },
                record["created_at"],
                "disposable_demo",
            )
        if kind == "artifact":
            artifact, raw = self.workflows.artifact(session, ctx, identifier)
            if artifact.mime == "application/json":
                text = json.loads(raw)["text"]
            else:
                parser = PlainDocument()
                parser.feed(raw.decode())
                text = "\n".join(parser.text)
            return (
                {
                    "text": text,
                    "artifact_id": identifier,
                    "workflow_run_id": artifact.workflow_run_id,
                    "origin_digest": bytes_digest(raw),
                    "core_run_id": artifact.core_run_id,
                    "agent_version_id": artifact.agent_version_id,
                    "model": artifact.model,
                },
                artifact.created_at,
                "verified_internal_snapshot",
            )
        row = RunStateRepository(session).get_run(ctx, identifier)
        result = self.core.stored_result(row)
        if not result.execution_claim_verified:
            raise HistoryUnverifiedError(
                "Historical run cannot authenticate evidence ingestion."
            )
        from packages.contracts.timestamps import canonical_timestamp

        return (
            {
                "text": result.output or "",
                "core_run_id": identifier,
                "status": result.status.value,
                "agent_version_id": result.agent_version_id,
                "model": result.model,
                "claim_attestation": row.execution_attestation,
            },
            canonical_timestamp(row.completed_at or row.created_at, stored=True),
            "verified_internal_snapshot",
        )

    def document(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:create")
            text = self.clean(body.text)
            _, document = self.add(
                session,
                ctx,
                DocumentRow,
                EvidenceDocument,
                "document",
                title=self.clean(body.title),
                text=text,
                digest=bytes_digest(text.encode()),
                sanitized=text != body.text,
            )
            source = self.ingest_in_session(
                session,
                ctx,
                {"kind": "document", "id": document["id"]},
                document["title"],
            )
            self.audit(
                session,
                ctx,
                "brief.document.ingested",
                document["id"],
                digest=document["digest"],
            )
            self.authorize(session, ctx, "version:create")
            return {"document": document, "source": source}

    def ingest_in_session(self, session, ctx, reference, title, max_age_seconds=86400):
        self.authorize(session, ctx, "version:create")
        origin, observed_at, quality = self.origin(session, ctx, reference)
        snapshot = dict(origin)
        if "text" in snapshot:
            snapshot["text"] = self.clean(snapshot["text"])
        raw = encoded(snapshot)
        if len(raw) > 65536:
            raise ValueError("Evidence exceeds the 64 KiB snapshot limit.")
        _, source = self.add(
            session,
            ctx,
            SourceRow,
            EvidenceSource,
            "source",
            blob=raw,
            title=self.clean(title),
            source_ref=reference,
            source_digest=digest(origin),
            digest=bytes_digest(raw),
            length=len(raw),
            mime="application/json",
            observed_at=observed_at,
            collected_at=now(),
            sanitized=snapshot != origin or origin.get("sanitized", False),
            quality=quality,
            max_age_seconds=max_age_seconds,
        )
        self.audit(
            session,
            ctx,
            "brief.source.ingested",
            source["id"],
            source_kind=source["source_ref"]["kind"],
            digest=source["digest"],
        )
        return source

    def ingest(self, ctx, body):
        with self.db.session(write=True) as session:
            return self.ingest_in_session(
                session,
                ctx,
                body.source_ref.model_dump(),
                body.title,
                body.max_age_seconds,
            )

    def source(self, session, ctx, identifier):
        row, source = self.get(session, SourceRow, ctx, identifier)
        raw = bytes(row.blob)
        if (
            len(raw) != source["length"]
            or len(raw) > 65536
            or bytes_digest(raw) != source["digest"]
            or source["mime"] != "application/json"
        ):
            raise HistoryUnverifiedError("Evidence snapshot integrity differs.")
        origin, _, _ = self.origin(session, ctx, source["source_ref"])
        if digest(origin) != source["source_digest"]:
            raise HistoryUnverifiedError("Original evidence reference changed.")
        data = json.loads(raw)
        expected = dict(origin)
        if "text" in expected:
            expected["text"] = self.clean(expected["text"])
        if data != expected:
            raise HistoryUnverifiedError(
                "Evidence content differs from its verified source."
            )
        observed = datetime.datetime.fromisoformat(
            source["observed_at"].replace("Z", "+00:00")
        )
        age = (datetime.datetime.now(datetime.timezone.utc) - observed).total_seconds()
        return (
            source,
            data,
            "fresh" if 0 <= age <= source["max_age_seconds"] else "stale",
        )

    def evaluate(self, session, ctx, bundle):
        hypothesis = bundle["hypothesis"]
        items, coverage = [], set()
        for identifier in bundle["source_ids"]:
            try:
                source, content, freshness = self.source(session, ctx, identifier)
                if source["digest"] != bundle["source_digests"][identifier]:
                    raise HistoryUnverifiedError("Bundle reference digest changed.")
                relationship, reason, applicable = (
                    "neutral",
                    "Source does not cover this typed hypothesis.",
                    False,
                )
                if (
                    hypothesis["predicate"] == "service_healthy"
                    and type(content.get("healthy")) is bool
                    and content.get("target_id") == hypothesis["target_id"]
                ):
                    relationship = "support" if content["healthy"] else "conflict"
                    reason, applicable = "Observed disposable service health.", True
                elif hypothesis["predicate"] == "contains_text" and isinstance(
                    content.get("text"), str
                ):
                    relationship = (
                        "support"
                        if hypothesis["text"].casefold() in content["text"].casefold()
                        else "neutral"
                    )
                    reason, applicable = (
                        "Literal text search in verified source; no inferred meaning.",
                        True,
                    )
                elif hypothesis["predicate"] == "run_completed" and content.get(
                    "status"
                ) in {"completed", "failed", "cancelled"}:
                    relationship = (
                        "support" if content["status"] == "completed" else "conflict"
                    )
                    reason, applicable = "Observed Core terminal run status.", True
                if applicable and freshness == "fresh":
                    coverage.add(
                        (source["source_ref"]["kind"], source["source_ref"]["id"])
                    )
                excerpt = str(
                    content.get("text", json.dumps(content, ensure_ascii=False))
                )[:2000]
                items.append(
                    EvidenceItem(
                        source_id=identifier,
                        relationship=relationship,
                        integrity="VERIFIED",
                        freshness=freshness,
                        observed_at=source["observed_at"],
                        collected_at=source["collected_at"],
                        excerpt=excerpt,
                        reason=reason,
                    ).model_dump()
                )
            except (
                HistoryUnverifiedError,
                EntityNotFoundError,
                ValueError,
                KeyError,
                TypeError,
            ):
                items.append(
                    EvidenceItem(
                        source_id=identifier,
                        relationship="neutral",
                        integrity="UNVERIFIED",
                        freshness="unavailable",
                        reason="Missing or changed source; its content cannot support a claim.",
                    ).model_dump()
                )
        insufficient = len(coverage) < hypothesis["minimum_sources"] or any(
            item["integrity"] != "VERIFIED" for item in items
        )
        active = [item for item in items if item["freshness"] == "fresh"]
        if insufficient:
            status, abstention = (
                "INSUFFICIENT_EVIDENCE",
                "Abstain: required fresh, verified source coverage is unavailable.",
            )
        elif any(item["relationship"] == "conflict" for item in active):
            status, abstention = "CONFLICTING", None
        elif any(item["relationship"] == "support" for item in active):
            status, abstention = "SUPPORTED", None
        else:
            status, abstention = (
                "NOT_FOUND",
                "Abstain: the literal observation was not found in verified covered sources.",
            )
        return {
            "status": status,
            "abstention": abstention,
            "items": items,
            "coverage": len(coverage),
            "required_coverage": hypothesis["minimum_sources"],
            "evaluated_at": now(),
        }

    def bundle_in_session(self, session, ctx, body):
        self.authorize(session, ctx, "version:create")
        if body.hypothesis.target_id:
            from database.schema import DemoFixtureModel

            self.get(session, DemoFixtureModel, ctx, body.hypothesis.target_id)
        source_digests = {}
        for identifier in body.source_ids:
            _, source = self.get(session, SourceRow, ctx, identifier)
            source_digests[identifier] = source["digest"]
        if body.workflow_run_id:
            self.workflows.get(session, WorkflowRunModel, ctx, body.workflow_run_id)
        fields = body.model_dump(mode="json")
        fields["title"] = self.clean(fields["title"])
        fields["hypothesis"]["question"] = self.clean(fields["hypothesis"]["question"])
        if fields["hypothesis"]["text"] != self.clean(fields["hypothesis"]["text"]):
            raise ValueError("Evidence search cannot retain credential values.")
        initial = {**fields, "source_digests": source_digests}
        evaluation = self.evaluate(session, ctx, initial)
        _, bundle = self.add(
            session,
            ctx,
            BundleRow,
            EvidenceBundle,
            "bundle",
            **initial,
            status=evaluation["status"],
            abstention=evaluation["abstention"],
            digest="0" * 64,
        )
        references = set()
        for identifier in body.source_ids:
            _, source = self.get(session, SourceRow, ctx, identifier)
            ref = source["source_ref"]
            if ref["kind"] in {"run", "artifact"}:
                references.add((ref["kind"], ref["id"]))
        if body.workflow_run_id:
            references.add(("workflow_run", body.workflow_run_id))
        for kind, identifier in references:
            self.link(session, ctx, bundle["id"], kind, identifier)
        return bundle, evaluation

    def link(self, session, ctx, bundle_id, kind, identifier):
        self.add(
            session,
            ctx,
            LinkRow,
            EvidenceLink,
            "evidence_link",
            bundle_id=bundle_id,
            reference_kind=kind,
            reference_id=identifier,
        )

    def related(self, ctx, kind, identifier, after="", limit=25):
        from database.schema import (
            RelayIncidentModel,
            RelayCapsuleModel,
            BenchReplayModel,
        )

        with self.db.session() as session:
            self.authorize(session, ctx)
            if kind == "run":
                RunStateRepository(session).get_run(ctx, identifier)
            elif kind == "artifact":
                self.workflows.artifact(session, ctx, identifier)
            elif kind == "workflow_run":
                self.workflows.get(session, WorkflowRunModel, ctx, identifier)
            else:
                self.get(
                    session,
                    {
                        "incident": RelayIncidentModel,
                        "capsule": RelayCapsuleModel,
                        "replay": BenchReplayModel,
                    }[kind],
                    ctx,
                    identifier,
                )
            links, cursor = self.page(
                session,
                ctx,
                LinkRow,
                after,
                limit,
                reference_kind=kind,
                reference_id=identifier,
            )
            return {
                "items": [
                    self.bundle_detail_in_session(session, ctx, link["bundle_id"])
                    for link in links
                ],
                "next": cursor,
            }

    def create_bundle(self, ctx, body):
        with self.db.session(write=True) as session:
            bundle, _ = self.bundle_in_session(session, ctx, body)
            self.audit(
                session,
                ctx,
                "brief.bundle.created",
                bundle["id"],
                digest=bundle["digest"],
                status=bundle["status"],
            )
            self.authorize(session, ctx, "version:create")
            return self.bundle_detail_in_session(session, ctx, bundle["id"])

    def bundle_detail_in_session(self, session, ctx, identifier):
        _, bundle = self.get(session, BundleRow, ctx, identifier)
        if bundle["digest"] != digest(
            {key: value for key, value in bundle.items() if key != "digest"}
        ):
            raise HistoryUnverifiedError("Immutable bundle digest differs.")
        evaluation = self.evaluate(session, ctx, bundle)
        workflow = None
        if bundle["workflow_run_id"]:
            _, workflow = self.workflows.get(
                session, WorkflowRunModel, ctx, bundle["workflow_run_id"]
            )
            workflow = {
                key: workflow[key] for key in ("id", "workflow_id", "version_id")
            }
        self.authorize(session, ctx)
        return {**bundle, "evaluation": evaluation, "workflow": workflow}

    def detail(self, ctx, identifier):
        with self.db.session() as session:
            return self.bundle_detail_in_session(session, ctx, identifier)

    def inventory(self, ctx, after="", limit=25, q="", status="", workflow_run_id=None):
        with self.db.session() as session:
            filters = {}
            if workflow_run_id:
                self.workflows.get(session, WorkflowRunModel, ctx, workflow_run_id)
                filters["workflow_run_id"] = workflow_run_id
            rows, cursor = self.page(
                session, ctx, BundleRow, after, limit, q, status, **filters
            )
            return {
                "items": [
                    {**row, "evaluation": self.evaluate(session, ctx, row)}
                    for row in rows
                ],
                "next": cursor,
            }
