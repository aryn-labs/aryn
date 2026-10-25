"""Bounded declarative authoring. No executable code, expressions or regex."""

from typing import Literal
from pydantic import Field, model_validator
from packages.contracts.intelligence import Contract, Record, Identifier, Digest
from packages.contracts.bench import BenchSuiteDefinition


class ScenarioDraft(Contract):
    scenario_id: Identifier
    name: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4000)
    expected_text: str = Field(default="", max_length=500)
    forbidden_text: str = Field(default="", max_length=500)
    tools: list[Identifier] = Field(default_factory=list, max_length=8)
    isolation: Literal["no_tools", "isolated_worker"] = "no_tools"
    timeout_seconds: int = Field(default=30, strict=True, ge=1, le=120)

    @model_validator(mode="after")
    def boundary(self):
        if not self.expected_text and not self.forbidden_text:
            raise ValueError("A scenario requires an explicit literal expected or forbidden observation.")
        if len(set(self.tools)) != len(self.tools) or any(not tool.startswith("aryn_native_") for tool in self.tools):
            raise ValueError("Scenario tools must be unique reviewed native tool identifiers.")
        if self.tools and self.isolation != "isolated_worker":
            raise ValueError("Native tools require an isolated worker.")
        return self


class SuiteDraft(Contract):
    family_key: Identifier
    evaluation_version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=32)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    previous_version_id: Identifier | None = None
    scenarios: list[ScenarioDraft] = Field(min_length=1, max_length=16)
    candidate_id: Identifier | None = None

    @model_validator(mode="after")
    def unique(self):
        if len({scenario.scenario_id for scenario in self.scenarios}) != len(self.scenarios):
            raise ValueError("Suite scenario IDs must be unique.")
        return self


class SuiteVersion(Record):
    family_key: Identifier
    evaluation_version: str
    previous_version_id: Identifier | None
    author_id: Identifier
    candidate_id: Identifier | None
    definition: BenchSuiteDefinition
    digest: Digest


class ReviewSuite(Contract):
    expected_digest: Digest
    reason: str = Field(min_length=1, max_length=1000)


class CandidateDraft(Contract):
    source_kind: Literal["capsule", "evaluation"]
    source_id: Identifier
    scenario: ScenarioDraft
    reason: str = Field(min_length=1, max_length=1000)


class ScenarioCandidate(Record):
    source_kind: Literal["capsule", "evaluation"]
    source_id: Identifier
    source_digest: Digest
    scenario: ScenarioDraft
    reason: str
    author_id: Identifier
    digest: Digest
