"""Typed editing contracts; working copies confer no governance authority."""
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.agent import (
    AgentBudgetPolicy, AgentConstraints, AgentEvaluationReference, AgentModelPolicy,
    AgentOutputContract, AgentToolPolicy,
)
from packages.contracts.bench import validate_output_contract
from packages.contracts.runtime import RunResult


class EditorContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OutputPolicy(AgentOutputContract, EditorContract):
    pass


class ConstraintsPolicy(AgentConstraints, EditorContract):
    pass


class ModelPolicy(AgentModelPolicy, EditorContract):
    allow_fallback: Literal[False] = False


class ToolPolicy(AgentToolPolicy, EditorContract):
    tool_grants: list[str] = Field(default_factory=list, max_length=0)
    deny_by_default: Literal[True] = True
    network_access: Literal[False] = False
    file_write_access: Literal[False] = False
    code_execution: Literal[False] = False

    @model_validator(mode="after")
    def retain_confinement(self):
        required = set(AgentToolPolicy().forbidden_tools)
        if not required.issubset({tool.lower() for tool in self.forbidden_tools}):
            raise ValueError("Existing forbidden tools must remain denied.")
        return self


class BudgetPolicy(AgentBudgetPolicy, EditorContract):
    pass


class EvaluationPolicy(AgentEvaluationReference, EditorContract):
    pass


class AgentDraft(EditorContract):
    version_number: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$", max_length=32)
    system_prompt: str = Field(min_length=20, max_length=12000)
    model: str = Field(min_length=1, max_length=128)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=128, le=4096)
    tool_grants: list[str] = Field(default_factory=list, max_length=0)
    schema_version: Literal["1.0.0"] = "1.0.0"
    role: str = Field(default="general_agent", min_length=1, max_length=64)
    objective: str = Field(default="", max_length=4000)
    owner: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_contract: OutputPolicy = Field(default_factory=OutputPolicy)
    constraints: ConstraintsPolicy = Field(default_factory=ConstraintsPolicy)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    model_policy: ModelPolicy
    budget_policy: BudgetPolicy = Field(default_factory=BudgetPolicy)
    evaluation_reference: EvaluationPolicy = Field(default_factory=EvaluationPolicy)

    @model_validator(mode="after")
    def canonical_consistency(self):
        policy = self.model_policy
        if (policy.primary_model, policy.temperature, policy.max_tokens) != (self.model, self.temperature, self.max_tokens):
            raise ValueError("Model policy and canonical model settings must agree.")
        validate_output_contract(self.output_contract)
        if len(json.dumps(self.model_dump(mode="json"), allow_nan=False).encode()) > 65536:
            raise ValueError("Definition must fit within 64 KiB.")
        return self


class WorkingCopyInput(EditorContract):
    expected_generation: int = Field(ge=0)
    definition: AgentDraft
    source_version_id: str | None = Field(default=None, max_length=64)


class GenerationInput(EditorContract):
    expected_generation: int = Field(ge=1)


class StopInput(EditorContract):
    pass


class StopReceipt(EditorContract):
    cancellation_confirmed: bool
    result: RunResult


class WorkingCopyView(EditorContract):
    organization_id: str
    project_id: str
    blueprint_id: str
    generation: int
    definition: AgentDraft | None
    source_version_id: str | None = None
    updated_at: str | None = None


SectionId = Literal["identity", "instructions", "model", "output", "constraints", "tools", "budget", "evaluation"]


class NodePosition(EditorContract):
    id: SectionId
    x: float = Field(ge=-10000, le=10000)
    y: float = Field(ge=-10000, le=10000)


class Viewport(EditorContract):
    x: float = Field(default=0, ge=-10000, le=10000)
    y: float = Field(default=0, ge=-10000, le=10000)
    zoom: float = Field(default=1, ge=0.1, le=4)


class LayoutInput(EditorContract):
    expected_generation: int = Field(ge=0)
    positions: list[NodePosition] = Field(default_factory=list, max_length=8)
    viewport: Viewport = Field(default_factory=Viewport)

    @model_validator(mode="after")
    def unique_sections(self):
        if len({node.id for node in self.positions}) != len(self.positions):
            raise ValueError("Layout sections must be unique.")
        return self


class LayoutView(EditorContract):
    generation: int
    positions: list[NodePosition]
    viewport: Viewport


class LifecycleProjection(EditorContract):
    organization_id: str
    project_id: str
    refreshed_at: str
    limit: int
    blueprints: list[dict[str, Any]]
    versions: list[dict[str, Any]]
    assignments: list[dict[str, Any]]
    evaluations: list[dict[str, Any]]
    evaluation_suites: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    audit: list[dict[str, Any]]
    runs: list[dict[str, Any]]
    accepted_baselines: list[dict[str, Any]]
    budget: dict[str, Any] | None
    permissions: dict[str, bool]
