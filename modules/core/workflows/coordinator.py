"""ARYN Core Run Coordinator.

The authoritative orchestrator for agent runs. Enforces permissions, budget checks,
audit trails, and lifecycle control around untrusted runtime adapters.
Frontend NEVER accesses Hermes directly; all requests flow through this coordinator.
Complies with ARYN-ARCH-001 Section 03 and AGENTS.md rules 3, 4, 5, 8.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from packages.contracts.core import AuditStatus, SecurityContext
from packages.contracts.runtime import (
    RunRequest,
    RunResult,
    RunStatus,
    RuntimeAdapter,
    RuntimeTrace,
)
import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.model_adapters.router import ModelRouter
from modules.core.audit.logger import AuditLogger
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.usage.engine import BudgetEngine, BudgetExceededError


class RunCoordinator:
    """Core authority governing runtime execution."""

    def __init__(
        self,
        runtime_adapter: RuntimeAdapter,
        permission_engine: Optional[PermissionEngine] = None,
        budget_engine: Optional[BudgetEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        model_router: Optional[Any] = None,
    ) -> None:
        self.runtime_adapter = runtime_adapter
        self.permission_engine = permission_engine or PermissionEngine()
        self.budget_engine = budget_engine or BudgetEngine()
        self.audit_logger = audit_logger or AuditLogger()
        if model_router is None:
            mr_cls = importlib.import_module("packages.model-adapters").ModelRouter
            self.model_router = mr_cls()
        else:
            self.model_router = model_router

    async def execute_managed_direct_turn(
        self,
        request: RunRequest,
        context: SecurityContext,
    ) -> RunResult:
        """Executes a direct turn under complete Core governance."""
        # 1. Authoritative Permissions Gate
        try:
            self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)
        except PermissionDeniedError as exc:
            self.audit_logger.record(
                event_type="core.run.denied",
                context=context,
                resource_id="run_request",
                status=AuditStatus.DENIED,
                payload={"reason": str(exc), "prompt": request.prompt},
            )
            raise

        # 2. Model Routing & Policy Validation (ADR-005: No silent fallback)
        spec = self.model_router.resolve_model(request.model)

        # 3. Budget & Quota Preflight Check
        try:
            self.budget_engine.check_preflight(context)
        except BudgetExceededError as exc:
            self.audit_logger.record(
                event_type="core.run.budget_exceeded",
                context=context,
                resource_id="run_request",
                status=AuditStatus.DENIED,
                payload={"reason": str(exc)},
            )
            raise

        # 4. Pre-execution Audit
        self.audit_logger.record(
            event_type="core.run.initiated",
            context=context,
            resource_id="run_request",
            status=AuditStatus.ALLOWED,
            payload={
                "model": spec.model_id,
                "provider": spec.provider.value,
                "prompt": request.prompt,
            },
        )

        # 5. Dispatch to Runtime Adapter
        try:
            if hasattr(self.runtime_adapter, "execute_direct_turn"):
                result = await self.runtime_adapter.execute_direct_turn(request, context)
            else:
                # Fallback to async run if adapter doesn't implement direct turn
                run_id = await self.runtime_adapter.start_run(request, context)
                result = await self.runtime_adapter.get_result(run_id, context)

            # 6. Post-execution Budget Usage Recording
            self.budget_engine.record_usage(context, result.usage)

            # 7. Post-execution Audit
            self.audit_logger.record(
                event_type="core.run.completed",
                context=context,
                resource_id=result.run_id,
                status=AuditStatus.COMPLETED,
                payload={
                    "status": result.status.value,
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "total_tokens": result.usage.total_tokens,
                    "model": result.model,
                },
            )
            return result

        except Exception as exc:
            self.audit_logger.record(
                event_type="core.run.failed",
                context=context,
                resource_id="run_execution",
                status=AuditStatus.FAILED,
                payload={"error": str(exc)},
            )
            raise

    async def start_managed_run(
        self,
        request: RunRequest,
        context: SecurityContext,
    ) -> str:
        """Starts an async run through Core governance."""
        # 1. Authoritative Permissions Gate
        self.permission_engine.enforce("run:create", context, context.organization_id, context.project_id)

        # 2. Model Routing Policy Validation
        spec = self.model_router.resolve_model(request.model)

        # 3. Budget Check
        self.budget_engine.check_preflight(context)

        # 4. Audit
        self.audit_logger.record(
            event_type="core.run.queued",
            context=context,
            resource_id="run_dispatch",
            status=AuditStatus.ALLOWED,
            payload={"model": spec.model_id, "prompt": request.prompt},
        )

        # 5. Dispatch
        run_id = await self.runtime_adapter.start_run(request, context)
        return run_id

    async def get_managed_result(
        self,
        run_id: str,
        context: SecurityContext,
    ) -> RunResult:
        """Retrieves run results with permission checks and audit."""
        self.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
        result = await self.runtime_adapter.get_result(run_id, context)

        if result.status == RunStatus.COMPLETED:
            self.budget_engine.record_usage(context, result.usage)
            self.audit_logger.record(
                event_type="core.run.polled_completed",
                context=context,
                resource_id=run_id,
                status=AuditStatus.COMPLETED,
                payload={"tokens": result.usage.total_tokens},
            )
        return result

    async def cancel_managed_run(
        self,
        run_id: str,
        context: SecurityContext,
    ) -> bool:
        """Cancels a run with permission check and audit."""
        self.permission_engine.enforce("run:cancel", context, context.organization_id, context.project_id)
        cancelled = await self.runtime_adapter.cancel_run(run_id, context)

        self.audit_logger.record(
            event_type="core.run.cancelled",
            context=context,
            resource_id=run_id,
            status=AuditStatus.CANCELLED,
            payload={"success": cancelled},
        )
        return cancelled

    async def get_managed_trace(
        self,
        run_id: str,
        context: SecurityContext,
    ) -> RuntimeTrace:
        """Retrieves execution trace with permission check."""
        self.permission_engine.enforce("run:trace", context, context.organization_id, context.project_id)
        trace = await self.runtime_adapter.get_trace(run_id, context)
        return trace
