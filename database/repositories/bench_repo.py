"""Repository for persistent Bench evaluations and quality gate results."""

from __future__ import annotations

import json
import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import BenchEvaluationModel, utc_now
from packages.contracts.core import SecurityContext
from packages.contracts.bench import BenchEvaluationResult
from modules.bench.quality_gate import BenchQualityGate, QualityGateFailedError
from database.repositories.agent_repo import AgentRepository
from packages.contracts.agent import AgentVersion
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    TenantIsolationError,
)


class BenchRepository:
    """Stores and retrieves bench evaluation outcomes with tenant isolation."""

    def __init__(self, session: Session, evidence_signer=None) -> None:
        self.session = session
        self.evidence_signer = evidence_signer

    def record_evaluation(
        self,
        context: SecurityContext,
        eval_result: BenchEvaluationResult,
    ) -> BenchEvaluationModel:
        version = AgentVersion.from_stored(AgentRepository(self.session).get_version(context, eval_result.version_id))
        self.verify_result(context, eval_result, version, context.actor.actor_id)
        details_str = json.dumps([r.model_dump() for r in eval_result.scenario_results], sort_keys=True)
        model = BenchEvaluationModel(
            id=eval_result.evaluation_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            blueprint_id=eval_result.blueprint_id,
            version_id=eval_result.version_id,
            passed=1 if eval_result.passed else 0,
            total_scenarios=eval_result.total_scenarios,
            passed_scenarios=eval_result.passed_scenarios,
            score=eval_result.score,
            details_json=details_str,
            evaluated_by=context.actor.actor_id,
            evaluated_at=datetime.datetime.fromisoformat(eval_result.evaluated_at),
            provenance_json=json.dumps({
                "evaluation_version": eval_result.evaluation_version,
                "requested_model": eval_result.requested_model,
                "payload_hash": eval_result.payload_hash,
                "suite_hash": eval_result.suite_hash,
                "runtime_adapter": eval_result.runtime_adapter,
                "attestation": eval_result.attestation,
                "evaluated_at": eval_result.evaluated_at,
            }, sort_keys=True),
        )
        self.session.add(model)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Evaluation record with id '{eval_result.evaluation_id}' already exists."
            ) from exc
        return model

    def verify_result(self, context, result, version, evaluated_by):
        BenchQualityGate.validate_evidence(result)
        if (result.blueprint_id != version.blueprint_id or result.version_id != version.id
                or result.payload_hash != version.payload_hash or result.requested_model != version.model
                or not self.evidence_signer
                or not self.evidence_signer.verify("bench", result.evidence_payload(
                    context.organization_id, context.project_id, evaluated_by), result.attestation)):
            raise QualityGateFailedError("Bench provenance is unverified or configuration differs.")

    def validate_stored(self, context, row, version):
        try:
            if row.passed not in {0, 1}:
                raise ValueError("Invalid stored pass indicator.")
            provenance = json.loads(row.provenance_json)
            result = BenchEvaluationResult(
                evaluation_id=row.id, blueprint_id=row.blueprint_id, version_id=row.version_id,
                passed=bool(row.passed), total_scenarios=row.total_scenarios,
                passed_scenarios=row.passed_scenarios, score=row.score,
                scenario_results=json.loads(row.details_json), **provenance,
            )
            stored_time = row.evaluated_at
            if stored_time.tzinfo is None:
                stored_time = stored_time.replace(tzinfo=datetime.timezone.utc)
            if stored_time != datetime.datetime.fromisoformat(result.evaluated_at):
                raise ValueError("Evaluation timestamp differs.")
            self.verify_result(context, result, version, row.evaluated_by)
            return result
        except (ValueError, TypeError) as exc:
            raise QualityGateFailedError("Stored Bench evidence is malformed or unverified.") from exc

    def get_evaluation(self, context: SecurityContext, evaluation_id: str) -> BenchEvaluationModel:
        evaluation = self.session.query(BenchEvaluationModel).filter_by(id=evaluation_id).first()
        if not evaluation:
            raise EntityNotFoundError(f"Bench evaluation '{evaluation_id}' not found.")
        if evaluation.organization_id != context.organization_id or evaluation.project_id != context.project_id:
            raise TenantIsolationError(
                f"Tenant boundary violation: Evaluation '{evaluation_id}' belongs to org/project "
                f"'{evaluation.organization_id}/{evaluation.project_id}', not context '{context.organization_id}/{context.project_id}'."
            )
        return evaluation

    def get_latest_passing_evaluation(
        self,
        context: SecurityContext,
        version_id: str,
    ) -> Optional[BenchEvaluationModel]:
        """Finds the most recent successful evaluation for a given agent version."""
        latest = (
            self.session.query(BenchEvaluationModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
                version_id=version_id,
            )
            .order_by(BenchEvaluationModel.evaluated_at.desc(), BenchEvaluationModel.id.desc())
            .first()
        )
        # A later failure invalidates an earlier pass. Never promote stale evidence.
        if not latest or not latest.passed:
            return None
        version = AgentVersion.from_stored(AgentRepository(self.session).get_version(context, version_id))
        if version.evaluation_id != latest.id:
            raise QualityGateFailedError("Latest evaluation differs from the version evidence reference.")
        BenchQualityGate().enforce(self.validate_stored(context, latest, version))
        return latest
