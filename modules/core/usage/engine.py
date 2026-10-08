"""ARYN Core Budget and Usage Engine.

Enforces execution budgets, turn limits, and token limits.
Supports both ephemeral in-memory tracking and persistent database repository storage.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rule 4.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from packages.contracts.core import BudgetRule, SecurityContext
from packages.contracts.runtime import RunUsage


class BudgetExceededError(Exception):
    """Raised when an operation would exceed authorized budget or quota."""
    pass


class BudgetEngine:
    """Manages and enforces budget allocations per organization/project."""

    def __init__(self, default_rule: Optional[BudgetRule] = None, db_manager: Optional[Any] = None) -> None:
        self.default_rule = default_rule or BudgetRule()
        self.db_manager = db_manager
        # In-memory tracking fallback
        self._cumulative_tokens: Dict[str, int] = {}

    def get_rule_for_context(self, context: SecurityContext) -> BudgetRule:
        if self.db_manager:
            from database.repositories.budget_repo import BudgetRepository
            with self.db_manager.session() as session:
                repo = BudgetRepository(session)
                b = repo.get_budget(context)
                if b:
                    return BudgetRule(
                        max_tokens_per_run=b.max_tokens_per_run,
                        max_turns=b.max_turns,
                        max_cost_usd=b.max_cost_usd,
                    )
        return self.default_rule

    def check_preflight(self, context: SecurityContext, estimated_tokens: int = 1000) -> None:
        rule = self.get_rule_for_context(context)
        if estimated_tokens > rule.max_tokens_per_run:
            raise BudgetExceededError(
                f"Requested task estimated tokens ({estimated_tokens}) exceeds maximum allowed per run ({rule.max_tokens_per_run})."
            )

    def record_usage(self, context: SecurityContext, usage: RunUsage) -> None:
        if usage.availability != "measured":
            raise BudgetExceededError("Estimated or missing usage cannot enter measured accounting.")
        key = f"{context.organization_id}:{context.project_id}"
        current = self._cumulative_tokens.get(key, 0)
        self._cumulative_tokens[key] = current + usage.total_tokens

        if self.db_manager:
            from database.repositories.budget_repo import BudgetRepository
            with self.db_manager.session() as session:
                repo = BudgetRepository(session)
                repo.record_usage(context, usage.total_tokens)

    def get_cumulative_tokens(self, context: SecurityContext) -> int:
        if self.db_manager:
            from database.repositories.budget_repo import BudgetRepository
            with self.db_manager.session() as session:
                repo = BudgetRepository(session)
                b = repo.get_budget(context)
                if b:
                    return b.cumulative_tokens
        key = f"{context.organization_id}:{context.project_id}"
        return self._cumulative_tokens.get(key, 0)
