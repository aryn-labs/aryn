"""Bench Runner executing isolated safety and quality evaluation suites.

Complies with ARYN-ARCH-001 Section 06 and AGENTS.md rule 6.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from packages.contracts.core import SecurityContext
from packages.contracts.agent import AgentVersion
from packages.contracts.bench import BenchEvaluationResult, BenchScenario, ScenarioResult
from packages.contracts.runtime import ModelUnavailableError, RunRequest, RunStatus, RuntimeAdapter
from modules.bench.scenarios import get_standard_research_bench_scenarios, research_suite_hash
from modules.bench.quality_gate import QualityGateFailedError


class BenchRunner:
    """Executes evaluation scenarios against an agent version under isolated conditions."""

    def __init__(self, runtime_adapter: RuntimeAdapter) -> None:
        self.runtime_adapter = runtime_adapter
        self.evidence_signer = None

    async def evaluate_agent_version(
        self,
        context: SecurityContext,
        version: AgentVersion,
        scenarios: Optional[List[BenchScenario]] = None,
        on_event: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> BenchEvaluationResult:
        version.verify_integrity()
        suite = get_standard_research_bench_scenarios()
        if scenarios is not None and scenarios != suite:
            raise QualityGateFailedError("The complete current research suite is mandatory.")
        caps = await self.runtime_adapter.capabilities()
        if not caps.tools_confined or caps.enabled_toolsets or version.tool_grants:
            raise QualityGateFailedError("Research Bench requires an isolated text runtime without tools.")
        await self.runtime_adapter.require_model_available(version.model)
        if on_event:
            ev = on_event("bench.started", {"version_id": version.id, "total_scenarios": len(suite)})
            if asyncio.iscoroutine(ev):
                await ev
        scenario_results: List[ScenarioResult] = []

        for idx, scen in enumerate(suite):
            if on_event:
                ev = on_event("scenario.started", {
                    "scenario_id": scen.scenario_id,
                    "name": scen.name,
                    "index": idx,
                })
                if asyncio.iscoroutine(ev):
                    await ev
            req = RunRequest(
                prompt=scen.prompt,
                system_instructions=version.system_prompt,
                model=version.model,
                temperature=version.temperature,
                max_tokens=version.max_tokens,
                metadata={"bench_evaluation": True, "scenario_id": scen.scenario_id},
            )

            start_t = time.perf_counter()
            passed = True
            failure_reason = None
            output = ""
            res = None

            try:
                if hasattr(self.runtime_adapter, "execute_direct_turn"):
                    res = await self.runtime_adapter.execute_direct_turn(req, context)
                else:
                    run_id = await self.runtime_adapter.start_run(req, context)
                    res = await self.runtime_adapter.get_result(run_id, context)

                latency = round(time.perf_counter() - start_t, 3)
                output = res.output or ""

                if res.status != RunStatus.COMPLETED:
                    passed = False
                    failure_reason = f"Runtime run status: {res.status.value}"
                if passed and res.model != version.model:
                    passed = False
                    failure_reason = "Runtime model differs from requested model."
                if passed and (min(res.usage.input_tokens, res.usage.output_tokens, res.usage.total_tokens) < 0
                               or res.usage.total_tokens != res.usage.input_tokens + res.usage.output_tokens):
                    passed = False
                    failure_reason = "Runtime usage is inconsistent."

                # 1. Check forbidden pattern
                if passed and scen.forbidden_pattern:
                    if re.search(scen.forbidden_pattern, output):
                        passed = False
                        failure_reason = f"Triggered forbidden pattern: {scen.forbidden_pattern}"

                # 2. Check expected pattern
                if passed and scen.expected_pattern:
                    if not re.search(scen.expected_pattern, output):
                        passed = False
                        failure_reason = f"Did not match expected pattern: {scen.expected_pattern}"

                # 3. Check latency threshold
                if passed and latency > scen.max_latency_seconds:
                    passed = False
                    failure_reason = f"Latency {latency}s exceeded max allowed {scen.max_latency_seconds}s"

            except ModelUnavailableError:
                # A provider rejection invalidates model readiness, not all four scenario answers.
                # Abort the suite instead of dispatching another three known-invalid requests.
                raise
            except Exception as exc:
                latency = round(time.perf_counter() - start_t, 3)
                passed = False
                # Runtime error bodies are untrusted and may include credentials.
                failure_reason = f"Execution exception: {type(exc).__name__}"

            scenario_results.append(
                ScenarioResult(
                    scenario_id=scen.scenario_id,
                    name=scen.name,
                    category=scen.category,
                    passed=passed,
                    score=1.0 if passed else 0.0,
                    actual_output=output,
                    latency_seconds=latency,
                    failure_reason=failure_reason,
                    actual_model=res.model if res else "",
                    runtime_status=res.status.value if res else "failed",
                    input_tokens=res.usage.input_tokens if res else 0,
                    output_tokens=res.usage.output_tokens if res else 0,
                    total_tokens=res.usage.total_tokens if res else 0,
                )
            )
            if on_event:
                ev = on_event("scenario.completed", {
                    "scenario_id": scen.scenario_id,
                    "name": scen.name,
                    "index": idx,
                    "passed": passed,
                    "score": 1.0 if passed else 0.0,
                    "latency_seconds": latency,
                    "actual_model": res.model if res else "",
                    "failure_reason": failure_reason,
                    "actual_output": output,
                    "total_tokens": res.usage.total_tokens if res else 0,
                })
                if asyncio.iscoroutine(ev):
                    await ev

        passed_count = sum(1 for r in scenario_results if r.passed)
        total_count = len(scenario_results)
        score = round(passed_count / total_count, 4) if total_count > 0 else 0.0
        overall_passed = (passed_count == total_count and total_count > 0)

        result = BenchEvaluationResult(
            evaluation_id=f"eval_{uuid.uuid4().hex[:16]}",
            blueprint_id=version.blueprint_id,
            version_id=version.id,
            passed=overall_passed,
            total_scenarios=total_count,
            passed_scenarios=passed_count,
            score=score,
            scenario_results=scenario_results,
            requested_model=version.model,
            payload_hash=version.payload_hash,
            suite_hash=research_suite_hash(),
            runtime_adapter=f"{type(self.runtime_adapter).__module__}.{type(self.runtime_adapter).__qualname__}",
        )
        if self.evidence_signer:
            result.attestation = self.evidence_signer.sign(
                "bench", result.evidence_payload(context.organization_id, context.project_id, context.actor.actor_id))
        if on_event:
            ev = on_event("bench.completed", result.model_dump())
            if asyncio.iscoroutine(ev):
                await ev
        return result
