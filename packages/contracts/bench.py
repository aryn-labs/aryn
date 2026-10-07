"""Domain contracts for Bench evaluation and quality gates.

Defines schemas for BenchScenario, ScenarioResult, and BenchEvaluationResult.
Complies with ARYN-ARCH-001 Section 06 and AGENTS.md rule 6.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Canonical Bench identifiers (single authority)
RESEARCH_SAFETY_SUITE_ID: str = "research-safety-1.2.0"
RESEARCH_SAFETY_SUITE_ALIAS: str = "research-safety"
RESEARCH_SAFETY_EVALUATION_VERSION: str = "1.2.0"

RESEARCH_SAFETY_SCENARIO_IDS: List[str] = [
    "scen_safety_injection_defense",
    "scen_tool_confinement_defense",
    "scen_research_accuracy_synthesis",
    "scen_grounded_abstention",
]

# Backward-compatible constant aliases
RESEARCH_BENCH_SUITE_ID: str = RESEARCH_SAFETY_SUITE_ID
RESEARCH_BENCH_VERSION: str = RESEARCH_SAFETY_EVALUATION_VERSION


class BenchSuiteManifest(BaseModel):
    """Canonical registry manifest for a benchmark suite."""
    suite_id: str
    evaluation_version: str
    aliases: List[str] = Field(default_factory=list)
    scenario_ids: List[str] = Field(default_factory=list)


BENCH_SUITE_MANIFESTS: Dict[str, BenchSuiteManifest] = {
    RESEARCH_SAFETY_SUITE_ID: BenchSuiteManifest(
        suite_id=RESEARCH_SAFETY_SUITE_ID,
        evaluation_version=RESEARCH_SAFETY_EVALUATION_VERSION,
        aliases=[RESEARCH_SAFETY_SUITE_ALIAS],
        scenario_ids=list(RESEARCH_SAFETY_SCENARIO_IDS),
    ),
}


def resolve_bench_suite_manifest(identifier: str) -> Optional[BenchSuiteManifest]:
    """Resolves canonical suite manifest by canonical ID or alias."""
    for manifest in BENCH_SUITE_MANIFESTS.values():
        if identifier == manifest.suite_id or identifier in manifest.aliases:
            return manifest
    return None


def get_supported_bench_suite_ids() -> List[str]:
    """Returns all recognized suite identifiers including canonical IDs and aliases."""
    ids: List[str] = []
    for manifest in BENCH_SUITE_MANIFESTS.values():
        ids.append(manifest.suite_id)
        ids.extend(manifest.aliases)
    return sorted(list(dict.fromkeys(ids)))


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


class BenchSuiteDefinition(BaseModel):
    """Authoritative Bench evaluation suite definition with executable scenarios."""
    suite_id: str
    evaluation_version: str
    name: str
    description: str
    scenarios: List[BenchScenario] = Field(default_factory=list)
    scenario_ids: List[str] = Field(default_factory=list)
    suite_hash: str = ""
    aliases: List[str] = Field(default_factory=list)


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
    suite_id: str = RESEARCH_SAFETY_SUITE_ID
    evaluation_version: str = RESEARCH_SAFETY_EVALUATION_VERSION
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
