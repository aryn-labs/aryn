"""Domain contracts for Bench evaluation and quality gates.

Defines schemas for BenchScenario, ScenarioResult, and BenchEvaluationResult.
Complies with ARYN-ARCH-001 Section 06 and AGENTS.md rule 6.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

RESEARCH_BENCH_SUITE_ID = "research-safety-1.2.0"
RESEARCH_BENCH_VERSION = "research-safety-1.2.0"

RESEARCH_SAFETY_SCENARIO_IDS: List[str] = [
    "scen_safety_injection_defense",
    "scen_tool_confinement_defense",
    "scen_research_accuracy_synthesis",
    "scen_grounded_abstention",
]


class BenchCategory(str, Enum):
    SAFETY = "safety"
    ACCURACY = "accuracy"
    TOOL_CONFINEMENT = "tool_confinement"
    ABSTENTION = "abstention"


class BenchScenario(BaseModel):
    """Specification of an evaluation scenario."""
    scenario_id: str
    name: str
    category: BenchCategory
    prompt: str
    expected_pattern: Optional[str] = None
    forbidden_pattern: Optional[str] = None
    min_score: float = 1.0
    max_latency_seconds: float = 30.0


class ScenarioResult(BaseModel):
    """Individual result from executing a scenario against an agent."""
    scenario_id: str
    name: str
    category: BenchCategory
    passed: bool
    score: float
    actual_output: str
    latency_seconds: float
    failure_reason: Optional[str] = None
    actual_model: str = ""
    runtime_status: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class BenchEvaluationResult(BaseModel):
    """Aggregated evaluation result for an agent version against a benchmark suite."""
    evaluation_id: str
    blueprint_id: str
    version_id: str
    passed: bool
    total_scenarios: int
    passed_scenarios: int
    score: float
    scenario_results: List[ScenarioResult] = Field(default_factory=list)
    suite_id: str = RESEARCH_BENCH_SUITE_ID
    evaluation_version: str = RESEARCH_BENCH_VERSION
    requested_model: str = ""
    payload_hash: str = ""
    suite_hash: str = ""
    runtime_adapter: str = ""
    attestation: str = ""
    evaluated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def evidence_payload(self, organization_id: str, project_id: str, evaluated_by: str) -> dict:
        return {"organization_id": organization_id, "project_id": project_id,
                "evaluated_by": evaluated_by,
                "result": self.model_dump(mode="json", exclude={"attestation"})}
