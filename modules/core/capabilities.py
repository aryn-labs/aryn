"""Effective read model of existing mediation; this registry grants nothing."""

from modules.core.records import SignedRecords
from modules.core.workflows.executor import now
from packages.contracts.automation import Capability, CapabilityRegistry


class Capabilities(SignedRecords):
    def read(self, ctx, mode, runtime_ready=False):
        with self.db.session() as session:
            self.authorize(session, ctx)

            def permitted(action):
                return self.permissions.evaluate(
                    action, ctx, ctx.organization_id, ctx.project_id, session=session
                ).allowed

            values = []
            for namespace, adapter, risk, action, requirements in (
                (
                    "aryn.artifact.read",
                    "scoped_database_artifacts",
                    "read",
                    "run:read",
                    ["authorized scoped reference", "verified digest"],
                ),
                (
                    "aryn.agent.text",
                    "core_assigned_text",
                    "governed_text",
                    "run:create",
                    [
                        "published pinned version",
                        "active signed assignment",
                        "runtime exact model",
                        "Core budget",
                        "empty tool grants",
                    ],
                ),
                (
                    "aryn.workflow.execute",
                    "core_durable_workflow",
                    "governed_text",
                    "run:create",
                    [
                        "frozen validated graph",
                        "pinned published agents",
                        "Core per-task budget",
                        "hash-bound deliverable review",
                    ],
                ),
                (
                    "aryn.relay.restart_demo",
                    "project_disposable_database_fixture",
                    "disposable_write",
                    "run:create",
                    [
                        "verified project-owned demo fixture",
                        "exact proposal/hash Core human approval",
                        "independent causal health verification",
                    ],
                ),
                (
                    "aryn.automation.schedule",
                    "core_single_owner_scheduler",
                    "governed_text",
                    "version:approve",
                    [
                        "human owner with current admin membership",
                        "exact schedule hash Core approval",
                        "single owner OS/advisory fence",
                        "per-occurrence Core admission",
                    ],
                ),
            ):
                allowed = permitted(action)
                missing = (
                    []
                    if risk in {"read", "disposable_write"} or runtime_ready
                    else [
                        "runtime readiness not verified; exact model must be checked at dispatch"
                    ]
                )
                values.append(
                    Capability(
                        namespace=namespace,
                        adapter=adapter,
                        modes=["local", "hosted"],
                        risk=risk,
                        available=True,
                        effective_permission=allowed,
                        requirements=requirements,
                        missing_prerequisites=missing,
                        disabled_reason="Core effective permission denied: " + action
                        if not allowed
                        else "; ".join(missing) or None,
                    )
                )
            for namespace in (
                "host.file",
                "host.browser",
                "host.network",
                "host.code",
                "hermes.native_jobs",
                "hermes.admin",
                "commercial.payment",
                "commercial.managed_ai",
            ):
                values.append(
                    Capability(
                        namespace=namespace,
                        adapter="unavailable",
                        modes=["local", "hosted"],
                        risk="privileged",
                        available=False,
                        effective_permission=False,
                        disabled_reason="Tidak ada mediation/approval/sandbox atau entitlement terverifikasi. Default deny.",
                        missing_prerequisites=[
                            "verified privileged mediation/security approval or commercial authority"
                        ],
                        requirements=[
                            "separate owner-approved security/commercial workstream"
                        ],
                    )
                )
            return CapabilityRegistry(
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                mode=mode,
                checked_at=now(),
                capabilities=values,
            ).model_dump(mode="json")
