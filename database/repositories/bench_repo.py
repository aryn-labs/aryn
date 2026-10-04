"""Repository for persistent Bench evaluations and quality gate results."""

from __future__ import annotations

import json
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import BenchEvaluationModel, utc_now
from packages.contracts.core import SecurityContext
from packages.contracts.bench import BenchEvaluationResult
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    TenantIsolationError,
)


class BenchRepository:
    """Stores and retrieves bench evaluation outcomes with tenant isolation."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_evaluation(
        self,
        context: SecurityContext,
        eval_result: BenchEvaluationResult,
    ) -> BenchEvaluationModel:
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
            evaluated_at=utc_now(),
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
        return (
            self.session.query(BenchEvaluationModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
                version_id=version_id,
                passed=1,
            )
            .order_by(BenchEvaluationModel.evaluated_at.desc())
            .first()
        )
