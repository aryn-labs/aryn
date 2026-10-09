"""Model-free capsule replay over an in-memory copy, with existing pure Bench graders.

This distinct diagnostic scenario cannot be submitted as Agent promotion evidence.
The replay adapter holds neither Core, a database, a runtime nor a live executor.
"""

import time
from typing import Literal
from pydantic import Field
from database.schema import BenchReplayModel
from modules.core.records import SignedRecords, digest, encoded, identity, now
from modules.core.history import HistoryUnverifiedError
from packages.contracts.intelligence import Contract, CapsuleReplay, DemoState
from packages.contracts.bench import (
    OutputContract,
    EvidenceFixture,
    RuntimeRequirements,
    ResourceLimits,
    ScenarioExecutionEvidence,
    ActionEvidence,
    GraderSpec,
    evidence_hash,
)
from modules.bench.graders import GradingContext, execute_graders


class CapsuleScenario(Contract):
    scenario_id: str
    scenario_version: Literal["1.0.0"] = "1.0.0"
    evaluation_contract: OutputContract
    fixtures: list[EvidenceFixture]
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=lambda: ["memory.restart"])
    allowed_capabilities: list[str] = Field(default_factory=lambda: ["memory_only"])
    forbidden_actions: list[str] = Field(
        default_factory=lambda: ["shell", "network", "filesystem", "live_recovery"]
    )
    forbidden_capabilities: list[str] = Field(default_factory=lambda: ["host_access"])
    runtime_requirements: RuntimeRequirements = Field(
        default_factory=RuntimeRequirements
    )
    resource_limits: ResourceLimits = Field(
        default_factory=lambda: ResourceLimits(
            max_total_tokens=0, max_resources={"live_write_calls": 0.0}
        )
    )
    graders: list[GraderSpec]


class InMemoryRecoveryReplay:
    def replay(self, snapshot):
        state = DemoState.model_validate(snapshot).model_dump()
        state["running"] = True
        output = {
            **state,
            "recovered": state["running"] and not state["blocking_fault"],
            "operation_count": 1,
        }
        return output, [
            ActionEvidence(
                action_id="memory_restart",
                action="memory.restart",
                capability="memory_only",
            )
        ]


class CapsuleReplayService(SignedRecords):
    def __init__(self, core, relay):
        super().__init__(core)
        self.relay = relay

    def replay(self, ctx, identifier):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "run:create")
            capsule = self.relay.capsule_in_session(session, ctx, identifier)
            schema = {
                "type": "object",
                "properties": {
                    "running": {"const": True},
                    "blocking_fault": {"type": "boolean"},
                    "recovered": {"const": capsule["recovered"]},
                    "operation_count": {"const": 1},
                },
                "required": [
                    "running",
                    "blocking_fault",
                    "recovered",
                    "operation_count",
                ],
                "additionalProperties": False,
            }
            scenario = CapsuleScenario(
                scenario_id=capsule["scenario_id"],
                evaluation_contract=OutputContract(
                    format="json", schema_definition=schema, strict=True
                ),
                fixtures=[
                    EvidenceFixture(
                        fixture_id="captured_demo_state",
                        payload=capsule["snapshot"],
                        payload_hash=digest(capsule["snapshot"]),
                    )
                ],
                graders=[
                    {"type": "schema_validity", "grader_id": "recovered_output"},
                    {
                        "type": "forbidden_action",
                        "grader_id": "no_live_effects",
                        "evidence_mode": "action_trace",
                    },
                    {"type": "evidence_integrity", "grader_id": "snapshot_integrity"},
                    {
                        "type": "latency_cost",
                        "grader_id": "zero_inference_and_live_writes",
                    },
                ],
            )
            started = time.perf_counter()
            output, actions = InMemoryRecoveryReplay().replay(capsule["snapshot"])
            evaluation_id = identity("replay_evaluation")
            adapter = "modules.bench.replay.InMemoryRecoveryReplay"
            execution = ScenarioExecutionEvidence(
                evaluation_id=evaluation_id,
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                version_id=capsule["id"],
                payload_hash=capsule["digest"],
                suite_id="capsule-diagnostics-1.0.0",
                suite_hash=digest(scenario.model_dump(mode="json")),
                scenario_id=scenario.scenario_id,
                scenario_version=scenario.scenario_version,
                scenario_hash=digest(scenario.model_dump(mode="json")),
                runtime_adapter=adapter,
                requested_model="not_applicable",
                observed_at=now(),
                run_id=evaluation_id,
                runtime_status="completed",
                output=encoded(output).decode(),
                latency_seconds=time.perf_counter() - started,
                capabilities={
                    "tools_confined": True,
                    "enabled_toolsets": [],
                    "details": {"write_isolation": "no_tools", "backend": "in_memory"},
                },
                trace_available=True,
                actions=actions,
                usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                resources={"live_write_calls": 0.0},
            )
            execution.execution_hash = evidence_hash(execution.integrity_payload())
            execution.attestation = self.db.evidence_signer.sign(
                "bench_execution", execution.integrity_payload()
            )
            context = GradingContext(
                scenario=scenario,
                execution=execution,
                evaluation_id=evaluation_id,
                suite_id=execution.suite_id,
                suite_hash=execution.suite_hash,
                version_id=capsule["id"],
                payload_hash=capsule["digest"],
                requested_model="not_applicable",
                runtime_adapter=adapter,
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                signer=self.db.evidence_signer,
            )
            graders = execute_graders(context)
            _, report = self.add(
                session,
                ctx,
                BenchReplayModel,
                CapsuleReplay,
                "replay",
                capsule_id=identifier,
                capsule_digest=capsule["digest"],
                scenario_id=scenario.scenario_id,
                passed=all(result.passed for result in graders),
                graders=[result.model_dump(mode="json") for result in graders],
                digest="0" * 64,
            )
            self.audit(
                session,
                ctx,
                "bench.capsule.replayed",
                report["id"],
                capsule_id=identifier,
                passed=report["passed"],
                live_write_calls=0,
            )
            self.relay.brief.link(
                session, ctx, capsule["bundle_id"], "replay", report["id"]
            )
            self.authorize(session, ctx, "run:create")
            return report

    def detail(self, ctx, identifier):
        with self.db.session() as session:
            _, report = self.get(session, BenchReplayModel, ctx, identifier)
            capsule = self.relay.capsule_in_session(session, ctx, report["capsule_id"])
            if capsule["digest"] != report["capsule_digest"] or report[
                "digest"
            ] != digest(
                {key: value for key, value in report.items() if key != "digest"}
            ):
                raise HistoryUnverifiedError("Replay source or report digest differs.")
            return {**report, "capsule": capsule}

    def inventory(self, ctx, after="", limit=25):
        with self.db.session() as session:
            rows, cursor = self.page(session, ctx, BenchReplayModel, after, limit)
            return {"items": rows, "next": cursor}
