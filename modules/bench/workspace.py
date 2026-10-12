"""Bounded evaluation read projection; existing Bench repositories retain authority."""

import json
from sqlalchemy import and_, or_
from database.schema import BenchEvaluationModel, AgentBlueprintModel
from database.repositories.agent_repo import AgentRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.bench_regression_repo import BenchRegressionRepository, timestamp
from database.repositories.exceptions import EntityNotFoundError
from modules.bench.quality_gate import QualityGateFailedError
from modules.bench.scenarios import get_bench_suite_registry
from modules.core.records import SignedRecords
from modules.core.history import HistoryUnverifiedError
from packages.contracts.agent import AgentVersion, VersionIntegrityError


def public(value):
    """Never export signature envelopes or runtime credentials as UI trace."""
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items()
                if key not in {"attestation", "claim_attestation", "execution_attestation"}}
    if isinstance(value, list):
        return [public(item) for item in value]
    return value


class BenchWorkspace(SignedRecords):
    def suites(self, ctx):
        with self.db.session() as session:
            self.authorize(session, ctx)
            return {"items": [public(suite.model_dump(mode="json"))
                              for suite in get_bench_suite_registry().suites()]}

    def project(self, session, ctx, row, detail=False):
        repo = BenchRepository(session, self.db.evidence_signer)
        stored = AgentRepository(session).get_version(ctx, row.version_id)
        blueprint = AgentRepository(session).get_blueprint(ctx, row.blueprint_id)
        verified, comparison, baseline = False, None, None
        try:
            version = AgentVersion.from_stored(stored)
            repo.validate_stored(ctx, row, version)
            verified = True
        except (QualityGateFailedError, VersionIntegrityError, HistoryUnverifiedError, ValueError):
            pass
        def decoded(raw, kind):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, kind) else kind()
            except (ValueError, TypeError):
                return kind()
        provenance = decoded(row.provenance_json, dict)
        if detail or verified:
            regression = BenchRegressionRepository(session, self.db.evidence_signer)
            try:
                comparison = public(regression.compare(ctx, row.version_id, row.id).model_dump(mode="json"))
                if detail:
                    current = regression.current(ctx, row.blueprint_id)
                    baseline = public(current.model_dump(mode="json", exclude={"suite_definition"})) if current else None
            except (QualityGateFailedError, VersionIntegrityError, HistoryUnverifiedError, ValueError):
                pass
        return self.clean(public({
            "id": row.id, "organization_id": ctx.organization_id, "project_id": ctx.project_id,
            "blueprint_id": row.blueprint_id, "blueprint_name": blueprint.name,
            "version_id": row.version_id, "version_number": stored.version_number,
            "version_status": stored.status, "passed": row.passed == 1, "verified": verified,
            "score": row.score, "passed_scenarios": row.passed_scenarios,
            "total_scenarios": row.total_scenarios, "evaluated_at": timestamp(row.evaluated_at),
            "suite_id": provenance.get("suite_id") or "unavailable",
            "evaluation_version": provenance.get("evaluation_version"),
            "requested_model": provenance.get("requested_model"),
            **({"regression": {key: comparison[key] for key in ("state", "reason", "promotion_blocked")}
                if comparison else None} if not detail else {}),
            **({"scenarios": decoded(row.details_json, list), "provenance": provenance,
                "regression": comparison, "baseline": baseline,
                "current_evaluation": stored.evaluation_id == row.id,
                "promotion_eligible": bool(verified and row.passed == 1 and stored.evaluation_id == row.id
                                           and comparison and not comparison["promotion_blocked"])} if detail else {}),
        }))

    def inventory(self, ctx, after="", limit=25, q="", blueprint_id="", version_id="", suite_id="", status=""):
        with self.db.session() as session:
            self.authorize(session, ctx)
            query = session.query(BenchEvaluationModel).join(
                AgentBlueprintModel, BenchEvaluationModel.blueprint_id == AgentBlueprintModel.id
            ).filter(BenchEvaluationModel.organization_id == ctx.organization_id,
                     BenchEvaluationModel.project_id == ctx.project_id,
                     AgentBlueprintModel.organization_id == ctx.organization_id,
                     AgentBlueprintModel.project_id == ctx.project_id)
            if blueprint_id:
                AgentRepository(session).get_blueprint(ctx, blueprint_id)
                query = query.filter(BenchEvaluationModel.blueprint_id == blueprint_id)
            if version_id:
                AgentRepository(session).get_version(ctx, version_id)
                query = query.filter(BenchEvaluationModel.version_id == version_id)
            if status:
                query = query.filter(BenchEvaluationModel.passed == (1 if status == "passed" else 0))
            if q:
                literal = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                query = query.filter(or_(AgentBlueprintModel.name.ilike("%" + literal + "%", escape="\\"),
                                         BenchEvaluationModel.id == q))
            # Suite is a signed provenance field, not a parallel registry or label match.
            if suite_id:
                query = query.filter(BenchEvaluationModel.provenance_json.contains('"suite_id": "' + suite_id + '"', autoescape=True))
            if after:
                cursor = BenchRepository(session, self.db.evidence_signer).get_evaluation(ctx, after)
                if blueprint_id and cursor.blueprint_id != blueprint_id or version_id and cursor.version_id != version_id:
                    raise EntityNotFoundError("Pagination scope differs.")
                query = query.filter(or_(BenchEvaluationModel.evaluated_at < cursor.evaluated_at,
                    and_(BenchEvaluationModel.evaluated_at == cursor.evaluated_at, BenchEvaluationModel.id < cursor.id)))
            rows = query.order_by(BenchEvaluationModel.evaluated_at.desc(), BenchEvaluationModel.id.desc()).limit(limit + 1).all()
            items = [self.project(session, ctx, row) for row in rows[:limit]]
            self.authorize(session, ctx)
            return {"items": items, "next": rows[limit - 1].id if len(rows) > limit else None}

    def detail(self, ctx, identifier):
        with self.db.session() as session:
            self.authorize(session, ctx)
            row = BenchRepository(session, self.db.evidence_signer).get_evaluation(ctx, identifier)
            result = self.project(session, ctx, row, True)
            self.authorize(session, ctx)
            return result
