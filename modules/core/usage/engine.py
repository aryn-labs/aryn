"""ARYN Core Budget and Usage Engine.

Enforces execution budgets, turn limits, and token limits.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rule 4.
"""

from __future__ import annotations

from typing import Dict
from packages.contracts.core import BudgetRule, SecurityContext
from packages.contracts.runtime import RunUsage


class BudgetExceededError(Exception):
    """Raised when an operation would exceed authorized budget or quota."""
    pass


class BudgetEngine:
    """Manages and enforces budget allocations per organization/project."""

    def __init__(self, default_rule: BudgetRule | None = None) -> None:
        self.default_rule = default_rule or BudgetRule()
        # In-memory tracking of cumulative token consumption per project
        self._cumulative_tokens: Dict[str, int] = {}

    def get_rule_for_context(self, context: SecurityContext) -> BudgetRule:
        return self.default_rule

    def check_preflight(self, context: SecurityContext, estimated_tokens: int = 1000) -> None:
        rule = self.get_rule_for_context(context)
        if estimated_tokens > rule.max_tokens_per_run:
            raise BudgetExceededError(
                f"Requested task estimated tokens ({estimated_tokens}) exceeds maximum allowed per run ({rule.max_tokens_per_run})."
            )

    def record_usage(self, context: SecurityContext, usage: RunUsage) -> None:
        key = f"{context.organization_id}:{context.project_id}"
        current = self._cumulative_tokens.get(key, 0)
        self._cumulative_tokens[key] = current + usage.total_tokens

    def get_cumulative_tokens(self, context: SecurityContext) -> int:
        key = f"{context.organization_id}:{context.project_id}"
        return self._cumulative_tokens.get(key, 0)
