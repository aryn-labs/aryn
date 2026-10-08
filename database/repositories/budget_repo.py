"""Repository for usage and budget tracking with deterministic limits.

Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rule 4.
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.schema import RunStateModel, UsageBudgetModel, utc_now
from packages.contracts.core import SecurityContext
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
        max_total_tokens: Optional[int] = 1000000,
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
                max_total_tokens=max_total_tokens,
            )
            try:
                with self.session.begin_nested():
                    self.session.add(budget)
                    self.session.flush()
            except IntegrityError:
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

    def authority_budgets(self, context):
        """Lock organization (*) first, then project; all Core consumers share this ledger."""
        self.get_or_create_budget(context)
        return self.session.query(UsageBudgetModel).filter(
            UsageBudgetModel.organization_id == context.organization_id,
            UsageBudgetModel.project_id.in_(["*", context.project_id]),
        ).order_by(UsageBudgetModel.project_id).with_for_update().populate_existing().all()

    def reserve(self, context, run, tokens):
        budgets = self.authority_budgets(context)
        legacy_query = self.session.query(RunStateModel).filter(
            RunStateModel.id != run.id,
            RunStateModel.organization_id == context.organization_id,
            RunStateModel.execution_owner_id.is_(None),
            RunStateModel.usage_availability == "unavailable",
            RunStateModel.status.in_(["queued", "started", "running", "stopping", "failed", "outcome_unknown"]),
        )
        if not any(b.project_id == "*" for b in budgets):
            legacy_query = legacy_query.filter(RunStateModel.project_id == context.project_id)
        legacy_unknown = legacy_query.first()
        if legacy_unknown:
            raise BudgetExceededError("Historical execution consumption is unverified; reconciliation is required.")
        for budget in budgets:
            if tokens > budget.max_tokens_per_run or (budget.max_total_tokens is not None and
                    budget.cumulative_tokens + budget.reserved_tokens + tokens > budget.max_total_tokens):
                raise BudgetExceededError("Effective Core token budget is exhausted.")
        for budget in budgets:
            budget.reserved_tokens += tokens
        run.reserved_tokens = tokens
        self.session.flush()

    def settle(self, context, run, usage):
        """Atomic with terminal transition. Unknown consumption keeps the reservation."""
        if run.usage_settled:
            return
        if usage.availability != "measured":
            return
        budgets = self.authority_budgets(context)
        for budget in budgets:
            budget.reserved_tokens -= run.reserved_tokens
            if budget.reserved_tokens < 0:
                raise BudgetExceededError("Reservation integrity is invalid.")
            budget.cumulative_tokens += usage.total_tokens
            # Monetary consumption is only accepted with measured, sourced evidence.
            if usage.cost_usd is not None and usage.cost_source:
                budget.cumulative_cost_usd += usage.cost_usd
        run.usage_availability = "measured"
        run.usage_cost_usd = usage.cost_usd if usage.cost_source else None
        run.usage_cost_source = usage.cost_source if usage.cost_usd is not None else None
        run.reserved_tokens = 0
        run.usage_settled = 1
        self.session.flush()

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
        self.session.query(UsageBudgetModel).filter_by(id=budget.id).update({
            "cumulative_tokens": UsageBudgetModel.cumulative_tokens + tokens,
            "cumulative_cost_usd": UsageBudgetModel.cumulative_cost_usd + cost_usd,
            "updated_at": utc_now(),
        }, synchronize_session=False)
        self.session.expire(budget)
        self.session.refresh(budget)
        return budget
