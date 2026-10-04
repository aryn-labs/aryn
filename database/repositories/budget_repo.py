"""Repository for usage and budget tracking with deterministic limits.

Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rule 4.
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import UsageBudgetModel, utc_now
from packages.contracts.core import BudgetRule, SecurityContext
from database.repositories.exceptions import DuplicateEntityError, EntityNotFoundError, TenantIsolationError
from modules.core.usage.engine import BudgetExceededError


class BudgetRepository:
    """Manages and enforces persistent budget and usage tracking per organization/project."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_budget(
        self,
        context: SecurityContext,
        max_tokens_per_run: int = 4096,
        max_turns: int = 10,
        max_cost_usd: float = 0.50,
    ) -> UsageBudgetModel:
        """Retrieves or initializes the budget allocation for a project."""
        budget = (
            self.session.query(UsageBudgetModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
            )
            .first()
        )
        if not budget:
            budget_id = f"bgt_{context.organization_id}_{context.project_id}"
            budget = UsageBudgetModel(
                id=budget_id,
                organization_id=context.organization_id,
                project_id=context.project_id,
                max_tokens_per_run=max_tokens_per_run,
                max_turns=max_turns,
                max_cost_usd=max_cost_usd,
                cumulative_tokens=0,
                cumulative_cost_usd=0.0,
            )
            self.session.add(budget)
            try:
                self.session.flush()
            except IntegrityError:
                self.session.rollback()
                budget = (
                    self.session.query(UsageBudgetModel)
                    .filter_by(
                        organization_id=context.organization_id,
                        project_id=context.project_id,
                    )
                    .one()
                )
        return budget

    def get_budget(self, context: SecurityContext) -> Optional[UsageBudgetModel]:
        return (
            self.session.query(UsageBudgetModel)
            .filter_by(
                organization_id=context.organization_id,
                project_id=context.project_id,
            )
            .first()
        )

    def set_budget(
        self,
        context: SecurityContext,
        max_tokens_per_run: int,
        max_turns: int = 10,
        max_cost_usd: float = 0.50,
    ) -> UsageBudgetModel:
        budget = self.get_or_create_budget(
            context,
            max_tokens_per_run=max_tokens_per_run,
            max_turns=max_turns,
            max_cost_usd=max_cost_usd,
        )
        budget.max_tokens_per_run = max_tokens_per_run
        budget.max_turns = max_turns
        budget.max_cost_usd = max_cost_usd
        budget.updated_at = utc_now()
        self.session.flush()
        return budget

    def check_preflight(self, context: SecurityContext, estimated_tokens: int = 1000) -> None:
        """Enforces preflight token checks against persistent budget rules."""
        budget = self.get_or_create_budget(context)
        if estimated_tokens > budget.max_tokens_per_run:
            raise BudgetExceededError(
                f"Requested task estimated tokens ({estimated_tokens}) exceeds maximum allowed per run ({budget.max_tokens_per_run}) "
                f"for project '{context.project_id}'."
            )

    def record_usage(self, context: SecurityContext, tokens: int, cost_usd: float = 0.0) -> UsageBudgetModel:
        """Records token and cost consumption into the persistent ledger."""
        budget = self.get_or_create_budget(context)
        budget.cumulative_tokens += tokens
        budget.cumulative_cost_usd += cost_usd
        budget.updated_at = utc_now()
        self.session.flush()
        return budget
