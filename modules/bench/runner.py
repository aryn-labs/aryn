"""Bench scenario execution over authoritative suites and deterministic graders."""
from __future__ import annotations

import asyncio
import datetime
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from packages.contracts.core import SecurityContext
from packages.contracts.agent import AgentVersion, AgentEvaluationReference
from packages.contracts.bench import BenchEvaluationResult, BenchScenario, ScenarioExecutionEvidence, SuiteAggregateResult, evidence_hash
from packages.contracts.runtime import ModelUnavailableError, RunRequest, RunStatus, RuntimeAdapter
from modules.bench.scenarios import get_bench_suite
from modules.bench.graders import execute_graders, validate_output_contract
from modules.bench.evidence import grading_context, normalize_observations
from modules.bench.aggregation import aggregate_scenario, aggregate_suite
from modules.bench.quality_gate import QualityGateFailedError


class BenchRunner:
    def __init__(self, runtime_adapter: RuntimeAdapter) -> None:
        self.runtime_adapter = runtime_adapter
        self.evidence_signer = None
        self.approval_authority = None

    def resolve_suite(self, version, scenarios=None):
        version.verify_integrity(require_canonical=True)
        reference = AgentEvaluationReference.model_validate(version.evaluation_reference.model_dump())
        suite = get_bench_suite(reference.suite_id)
        if suite is None:
            raise QualityGateFailedError("Unknown authoritative evaluation suite.")
        if scenarios is not None and scenarios != suite.scenarios:
            raise QualityGateFailedError(f"The complete current suite '{suite.suite_id}' is mandatory.")
        validate_output_contract(version.output_contract)
        if (version.output_contract.format == "json" or version.output_contract.schema_definition
                or version.output_contract.required_sections):
            if any("schema_validity" not in {g.type for g in s.graders} for s in suite.scenarios):
                raise QualityGateFailedError("Agent output contract requires schema grading in every scenario.")
        return suite

    async def _execute(self, request, context):
        if hasattr(self.runtime_adapter, "execute_direct_turn"):
            return await self.runtime_adapter.execute_direct_turn(request, context)
        run_id = await self.runtime_adapter.start_run(request, context)
        while True:
            result = await self.runtime_adapter.get_result(run_id, context)
            if result.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return result
            await asyncio.sleep(0.02)

    async def evaluate_agent_version(self, context: SecurityContext, version: AgentVersion,
        scenarios: Optional[List[BenchScenario]] = None,
        on_event: Optional[Callable[[str, Dict[str, Any]], Any]] = None) -> BenchEvaluationResult:
        suite = self.resolve_suite(version, scenarios)
        caps = await self.runtime_adapter.capabilities()
        for scenario in suite.scenarios:
            grants = set(scenario.allowed_tools) & set(version.tool_grants)
            if not caps.tools_confined or not set(caps.enabled_toolsets).issubset(grants):
                raise QualityGateFailedError("Bench requires explicit tool grants and a confined runtime.")
            if scenario.runtime_requirements.write_isolation == "no_tools" and (caps.enabled_toolsets or version.tool_grants):
                raise QualityGateFailedError("This suite requires an isolated runtime without tools.")
            if scenario.runtime_requirements.write_isolation == "mocked" and caps.details.get("write_isolation") != "mocked":
                raise QualityGateFailedError("Bench requires verified mocked write isolation.")
        await self.runtime_adapter.require_model_available(version.model)
        result = BenchEvaluationResult(
            evaluation_id=f"eval_{uuid.uuid4().hex[:16]}", blueprint_id=version.blueprint_id,
            version_id=version.id, passed=False, total_scenarios=len(suite.scenarios), passed_scenarios=0, score=0,
            suite_id=suite.suite_id, evaluation_version=suite.evaluation_version,
            payload_hash=version.payload_hash, suite_hash=suite.suite_hash, requested_model=version.model,
            runtime_adapter=f"{type(self.runtime_adapter).__module__}.{type(self.runtime_adapter).__qualname__}",
            evidence_format=2, evaluation_reference=version.evaluation_reference.model_copy(deep=True), output_contract=version.output_contract.model_copy(deep=True),
            agent_tool_grants=list(version.tool_grants),
            agent_forbidden_actions=list(dict.fromkeys([*version.constraints.disallowed_actions])),
        )
        async def emit(name, payload):
            if on_event:
                emitted = on_event(name, payload)
                if asyncio.iscoroutine(emitted):
                    await emitted
        await emit("bench.started", {"version_id": version.id, "suite_id": suite.suite_id,
                                    "total_scenarios": len(suite.scenarios),
                                    "scenarios": [{"scenario_id": s.scenario_id, "name": s.name,
                                                   "category": s.category} for s in suite.scenarios]})
        for index, scenario in enumerate(suite.scenarios):
            await emit("scenario.started", {"scenario_id": scenario.scenario_id, "name": scenario.name, "index": index})
            limits = [version.budget_policy.timeout_seconds, version.constraints.max_execution_time_seconds,
                      scenario.max_latency_seconds]
            if suite.resource_limits.max_latency_seconds is not None:
                limits.append(suite.resource_limits.max_latency_seconds)
            timeout = min(limits)
            request = RunRequest(prompt=scenario.prompt, system_instructions=version.system_prompt,
                                 model=version.model, temperature=version.temperature, max_tokens=version.max_tokens,
                                 timeout_seconds=timeout,
                                 metadata={"bench_evaluation": True, "evaluation_id": result.evaluation_id,
                                           "suite_id": suite.suite_id, "scenario_id": scenario.scenario_id,
                                           "fixtures": [f.model_dump(mode="json") for f in scenario.fixtures]})
            execution = ScenarioExecutionEvidence(
                evaluation_id=result.evaluation_id, organization_id=context.organization_id, project_id=context.project_id,
                version_id=version.id, payload_hash=version.payload_hash, suite_id=suite.suite_id, suite_hash=suite.suite_hash,
                scenario_id=scenario.scenario_id, scenario_version=scenario.scenario_version,
                scenario_hash=evidence_hash(scenario.model_dump(mode="json")), runtime_adapter=result.runtime_adapter,
                requested_model=version.model, observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                runtime_status="failed", latency_seconds=0, capabilities=caps.model_dump(mode="json"),
            )
            started = time.perf_counter()
            try:
                observed = await asyncio.wait_for(self._execute(request, context), timeout=timeout)
                execution.run_id = observed.run_id
                execution.runtime_status = observed.status.value
                execution.output = observed.output
                execution.reported_model = observed.model
                execution.actual_model = observed.actual_model
                execution.runtime_requested_model = observed.requested_model
                execution.provider = observed.provider
                execution.runtime_backend = observed.runtime_backend
                execution.gateway = observed.gateway
                execution.usage = observed.usage.model_dump(mode="json")
                normalize_observations(execution, observed)
                if any(g.type == "forbidden_action" and g.evidence_mode == "action_trace" for g in scenario.graders) and not execution.trace_available:
                    try:
                        trace = await self.runtime_adapter.get_trace(observed.run_id, context)
                    except Exception:
                        trace = None
                    if trace is None:
                        execution.trace_available = False
                    elif trace.run_id != observed.run_id:
                        execution.trace_error = "trace_identity_mismatch"
                    elif trace.available:
                        # Only explicit complete structured traces can prove action absence.
                        if trace.raw_trace is None or trace.raw_trace.get("complete") is not True:
                            execution.trace_error = "trace_completeness_missing"
                        else:
                            from pydantic import TypeAdapter
                            from packages.contracts.bench import ActionEvidence
                            try:
                                execution.actions = TypeAdapter(list[ActionEvidence]).validate_python(trace.events, strict=True)
                                execution.trace_available = True
                            except (ValueError, TypeError):
                                execution.trace_error = "action_trace_malformed"
            except ModelUnavailableError:
                raise
            except Exception as exc:
                execution.runtime_status = "failed"
                execution.runtime_error = type(exc).__name__
            execution.latency_seconds = round(time.perf_counter() - started, 3)
            for spec in scenario.graders:
                if spec.type == "approval_enforcement" and self.approval_authority:
                    try:
                        requirement = spec.requirement
                        record = self.approval_authority.verify_approval(context, requirement.target_type,
                            requirement.target_id, requirement.payload_hash)
                        execution.approval_records.append(record.model_dump(mode="json"))
                    except Exception:
                        pass  # Missing/unverified Core authority produces an explicit failing grader.
            execution.execution_hash = evidence_hash(execution.integrity_payload())
            if self.evidence_signer:
                execution.attestation = self.evidence_signer.sign("bench_execution", execution.integrity_payload())
            ctx = grading_context(result, scenario, execution, signer=self.evidence_signer, approval_authority=self.approval_authority)
            graders = execute_graders(ctx, suite.resource_limits)
            scenario_result = aggregate_scenario(scenario, execution, graders)
            result.scenario_results.append(scenario_result)
            await emit("scenario.completed", {**scenario_result.model_dump(mode="json"), "index": index})
        suite_count, suite_score, suite_state, suite_decision = aggregate_suite(suite, result.scenario_results)
        result.suite_aggregate = SuiteAggregateResult(passed=suite_decision.passed, total_scenarios=len(suite.scenarios),
            passed_scenarios=suite_count, score=suite_score, state=suite_state)
        count, score, state, decision = aggregate_suite(suite, result.scenario_results, version.evaluation_reference)
        result.passed_scenarios, result.score, result.state, result.quality_gate = count, score, state, decision
        result.passed = decision.passed
        if self.evidence_signer:
            result.attestation = self.evidence_signer.sign("bench", result.evidence_payload(
                context.organization_id, context.project_id, context.actor.actor_id))
        await emit("bench.completed", result.model_dump(mode="json"))
        return result
