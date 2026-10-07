"""Versioned contracts for reusable Bench execution, grading and provenance."""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

# Compatibility defaults for existing canonical agent payloads. Suite authority lives in Bench.
RESEARCH_SAFETY_SUITE_ID = "research-safety-1.2.0"
RESEARCH_SAFETY_SUITE_ALIAS = "research-safety"
RESEARCH_SAFETY_EVALUATION_VERSION = "1.2.0"
RESEARCH_SAFETY_SCENARIO_IDS = ["scen_safety_injection_defense", "scen_tool_confinement_defense",
                              "scen_research_accuracy_synthesis", "scen_grounded_abstention"]
RESEARCH_BENCH_SUITE_ID = RESEARCH_SAFETY_SUITE_ID
RESEARCH_BENCH_VERSION = RESEARCH_SAFETY_EVALUATION_VERSION


def evidence_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


class BenchContract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class OutputContract(BaseModel):
    """Shared output contract; AgentOutputContract remains an import alias."""
    format: str = "text"
    schema_definition: Optional[Dict[str, Any]] = None
    required_sections: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    strict: bool = False


def validate_output_contract(contract: OutputContract | None):
    if contract is None:
        return
    if contract.format not in {"text", "markdown", "json"}:
        raise ValueError("Unsupported output format.")
    schema = contract.schema_definition
    if schema is None:
        return
    if contract.format != "json":
        raise ValueError("Structured schemas require JSON output.")
    resolver = Registry().with_resource("urn:aryn:evaluation", Resource.from_contents(
        schema, default_specification=DRAFT202012)).resolver("urn:aryn:evaluation")
    def check(value):
        if isinstance(value, dict):
            if "$id" in value:
                raise ValueError("Evaluation schemas use one local reference root.")
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"} and (not isinstance(child, str) or not child.startswith("#")):
                    raise ValueError("Evaluation schemas cannot resolve external references.")
                if key in {"$ref", "$dynamicRef"}:
                    try:
                        resolver.lookup(child)
                    except Exception as exc:
                        raise ValueError("Evaluation schema reference cannot be resolved locally.") from exc
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(schema)
    if schema.get("$schema", "https://json-schema.org/draft/2020-12/schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("Bench output schemas use JSON Schema 2020-12.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError("Invalid evaluation output schema.") from exc


class EvaluationState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    POLICY_VIOLATION = "policy_violation"
    UNVERIFIABLE = "unverifiable"
    INVALID_EVIDENCE = "invalid_evidence"
    RUNTIME_ERROR = "runtime_error"


class BenchCategory(str, Enum):
    SAFETY = "safety"
    ACCURACY = "accuracy"
    TOOL_CONFINEMENT = "tool_confinement"
    ABSTENTION = "abstention"


class GraderSpecification(BenchContract):
    grader_id: str = Field(min_length=1)
    version: Literal["1.0.0"] = "1.0.0"


class SchemaGraderSpec(GraderSpecification):
    type: Literal["schema_validity"] = "schema_validity"


class ForbiddenActionGraderSpec(GraderSpecification):
    type: Literal["forbidden_action"] = "forbidden_action"
    evidence_mode: Literal["confinement", "action_trace"] = "confinement"


class ApprovalRequirement(BenchContract):
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_id: Optional[str] = None
    allowed_actors: List[str] = Field(default_factory=list)
    max_age_seconds: float = Field(default=3600, gt=0)


class ApprovalGraderSpec(GraderSpecification):
    type: Literal["approval_enforcement"] = "approval_enforcement"
    requirement: ApprovalRequirement


class IdempotencyGraderSpec(GraderSpecification):
    type: Literal["idempotency"] = "idempotency"
    idempotency_key: str = Field(min_length=1)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    min_observations: int = Field(default=2, ge=2)


class ModelIdentityGraderSpec(GraderSpecification):
    type: Literal["model_identity"] = "model_identity"
    provider: Optional[str] = None
    runtime_backend: Optional[str] = None
    gateway: Optional[str] = None


class ResourceLimits(BenchContract):
    max_latency_seconds: Optional[float] = Field(default=None, gt=0, strict=True)
    max_total_tokens: Optional[int] = Field(default=None, ge=0, strict=True)
    max_cost_usd: Optional[float] = Field(default=None, ge=0, strict=True)
    max_resources: Dict[str, Annotated[float, Field(strict=True)]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_resources(self):
        if any(not name or value < 0 for name, value in self.max_resources.items()):
            raise ValueError("Resource names and limits must be valid.")
        return self


class LatencyCostGraderSpec(GraderSpecification):
    type: Literal["latency_cost"] = "latency_cost"
    limits: ResourceLimits = Field(default_factory=ResourceLimits)


class EvidenceIntegrityGraderSpec(GraderSpecification):
    type: Literal["evidence_integrity"] = "evidence_integrity"


class TextPatternGraderSpec(GraderSpecification):
    type: Literal["text_pattern"] = "text_pattern"
    expected_pattern: Optional[str] = None
    forbidden_pattern: Optional[str] = None

    @model_validator(mode="after")
    def valid_patterns(self):
        if not self.expected_pattern and not self.forbidden_pattern:
            raise ValueError("A content grader requires a pattern.")
        for pattern in (self.expected_pattern, self.forbidden_pattern):
            if pattern is not None:
                re.compile(pattern)
        return self


GraderSpec = Annotated[Union[SchemaGraderSpec, ForbiddenActionGraderSpec, ApprovalGraderSpec,
    IdempotencyGraderSpec, ModelIdentityGraderSpec, LatencyCostGraderSpec,
    EvidenceIntegrityGraderSpec, TextPatternGraderSpec], Field(discriminator="type")]


class RuntimeRequirements(BenchContract):
    tools_confined: Literal[True] = True
    write_isolation: Literal["no_tools", "mocked"] = "no_tools"
    runtime_backend: Optional[str] = None


class EvidenceFixture(BenchContract):
    fixture_id: str = Field(min_length=1)
    payload: Dict[str, Any]
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_hash(self):
        if evidence_hash(self.payload) != self.payload_hash:
            raise ValueError("Fixture payload hash differs.")
        return self


class BenchScenario(BenchContract):
    """Generic scenario; descriptive outcomes/rules are not proof of enforcement."""
    scenario_id: str = Field(min_length=1)
    scenario_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    schema_version: Literal["2.0.0"] = "2.0.0"
    name: str = Field(min_length=1)
    description: str = ""
    category: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected_outcomes: List[str] = Field(default_factory=list)
    allowed_actions: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)
    allowed_capabilities: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
    forbidden_capabilities: List[str] = Field(default_factory=list)
    safety_constraints: List[str] = Field(default_factory=list)
    evaluation_contract: Optional[OutputContract] = None
    graders: List[GraderSpec] = Field(min_length=1)
    runtime_requirements: RuntimeRequirements = Field(default_factory=RuntimeRequirements)
    fixtures: List[EvidenceFixture] = Field(default_factory=list)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    min_score: float = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def valid_scenario(self):
        validate_output_contract(self.evaluation_contract)
        ids = [spec.grader_id for spec in self.graders]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate grader identities.")
        required = {"model_identity", "evidence_integrity", "forbidden_action", "latency_cost"}
        if not required.issubset({spec.type for spec in self.graders}):
            raise ValueError("Scenarios require identity, integrity, confinement and resource graders.")
        if self.evaluation_contract and "schema_validity" not in {s.type for s in self.graders}:
            raise ValueError("An output contract requires schema grading.")
        for values in (self.allowed_actions, self.allowed_tools, self.allowed_capabilities, self.forbidden_actions, self.forbidden_capabilities):
            if any(not value or value != value.strip() for value in values) or len(values) != len(set(values)):
                raise ValueError("Boundary identifiers must be nonempty and unique.")
        if (set(self.allowed_actions) | set(self.allowed_tools)) & set(self.forbidden_actions):
            raise ValueError("A forbidden tool cannot be granted.")
        if set(self.allowed_capabilities) & set(self.forbidden_capabilities):
            raise ValueError("A forbidden capability cannot be granted.")
        if self.allowed_tools and self.runtime_requirements.write_isolation != "mocked":
            raise ValueError("Evaluation tools require isolated mocked writes.")
        if len({f.fixture_id for f in self.fixtures}) != len(self.fixtures):
            raise ValueError("Duplicate fixture identities.")
        return self

    # Read compatibility for callers inspecting Research Safety patterns.
    @property
    def expected_pattern(self):
        return next((g.expected_pattern for g in self.graders if g.type == "text_pattern"), None)

    @property
    def forbidden_pattern(self):
        return next((g.forbidden_pattern for g in self.graders if g.type == "text_pattern"), None)

    @property
    def max_latency_seconds(self):
        return self.resource_limits.max_latency_seconds or 30.0


class BenchSuiteManifest(BenchContract):
    suite_id: str = Field(min_length=1)
    evaluation_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    aliases: List[str] = Field(default_factory=list)
    scenario_ids: List[str] = Field(min_length=1)


class BenchSuiteDefinition(BenchSuiteManifest):
    name: str = Field(min_length=1)
    description: str
    scenarios: List[BenchScenario] = Field(min_length=1)
    min_score_threshold: float = Field(default=1, ge=0, le=1)
    required_scenarios: List[str] = Field(default_factory=list)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    suite_hash: str = ""
    legacy_suite_hash: Optional[str] = None

    @model_validator(mode="after")
    def valid_suite(self):
        ids = [s.scenario_id for s in self.scenarios]
        if ids != self.scenario_ids or len(ids) != len(set(ids)):
            raise ValueError("Suite scenario identities must be unique and ordered.")
        if "required_scenarios" not in self.model_fields_set:
            object.__setattr__(self, "required_scenarios", list(ids))
        if len(set(self.required_scenarios)) != len(self.required_scenarios):
            raise ValueError("Duplicate required scenario identities.")
        if not set(self.required_scenarios).issubset(ids):
            raise ValueError("Required scenarios must belong to the suite.")
        digest = evidence_hash(self.model_dump(mode="json", exclude={"suite_hash"}))
        if self.suite_hash and self.suite_hash != digest:
            raise ValueError("Suite configuration hash differs.")
        object.__setattr__(self, "suite_hash", digest)
        return self


class ActionEvidence(BenchContract):
    action_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    tool: Optional[str] = None
    capability: Optional[str] = None
    side_effect_id: Optional[str] = None


class IdempotencyObservation(BenchContract):
    organization_id: str
    project_id: str
    idempotency_key: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    side_effect_ids: List[str]
    emitted_side_effect_ids: List[str]
    replayed: bool


class ScenarioExecutionEvidence(BenchContract):
    """Adapter observations bound and signed by Bench, never a runtime PASS claim."""
    evaluation_id: str
    organization_id: str
    project_id: str
    version_id: str
    payload_hash: str
    suite_id: str
    suite_hash: str
    scenario_id: str
    scenario_version: str
    scenario_hash: str
    runtime_adapter: str
    requested_model: str
    observed_at: str
    run_id: str = ""
    runtime_status: str
    output: str = ""
    latency_seconds: float = Field(ge=0, strict=True)
    reported_model: str = ""
    actual_model: Optional[str] = None
    runtime_requested_model: Optional[str] = None
    provider: Optional[str] = None
    runtime_backend: Optional[str] = None
    gateway: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    cost_usd: Optional[float] = Field(default=None, ge=0, strict=True)
    resources: Dict[str, Annotated[float, Field(strict=True)]] = Field(default_factory=dict)
    capabilities: Optional[Dict[str, Any]] = None
    trace_available: bool = False
    actions: List[ActionEvidence] = Field(default_factory=list)
    trace_error: Optional[str] = None
    idempotency_observations: List[IdempotencyObservation] = Field(default_factory=list)
    approval_records: List[Dict[str, Any]] = Field(default_factory=list)
    runtime_error: Optional[str] = None
    evidence_errors: List[str] = Field(default_factory=list)
    execution_hash: str = ""
    attestation: str = ""

    @model_validator(mode="after")
    def valid_observation_time(self):
        observed = datetime.datetime.fromisoformat(self.observed_at)
        if observed.tzinfo is None:
            raise ValueError("Observation time must include timezone provenance.")
        return self

    def integrity_payload(self):
        return self.model_dump(mode="json", exclude={"execution_hash", "attestation"})


class GraderResult(BenchContract):
    grader_id: str
    grader_type: str
    grader_version: str = "1.0.0"
    state: EvaluationState
    passed: bool
    reason: str
    details: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_state(self):
        if self.passed != (self.state == EvaluationState.PASSED):
            raise ValueError("Grader state and pass indicator differ.")
        return self


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    scenario_id: str
    name: str
    category: str
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
    scenario_version: str = "1.0.0"
    state: EvaluationState = EvaluationState.UNVERIFIABLE
    execution: Optional[ScenarioExecutionEvidence] = None
    grader_results: List[GraderResult] = Field(default_factory=list)


class QualityGateDecision(BenchContract):
    passed: bool
    reason: str
    min_score_threshold: float
    required_scenarios: List[str]


class EvaluationReference(BaseModel):
    """Evaluation suite and quality gate requirements for Bench promotion."""
    suite_id: str = RESEARCH_SAFETY_SUITE_ID
    evaluation_version: str = RESEARCH_SAFETY_EVALUATION_VERSION
    min_score_threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    required_scenarios: List[str] = Field(
        default_factory=lambda: list(RESEARCH_SAFETY_SCENARIO_IDS)
    )
    evaluation_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _suite_defaults(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            manifest = resolve_bench_suite_manifest(values.get("suite_id", RESEARCH_SAFETY_SUITE_ID))
            if manifest is not None:
                values.setdefault("evaluation_version", manifest.evaluation_version)
                values.setdefault("required_scenarios", list(manifest.scenario_ids))
        return values

    @model_validator(mode="after")
    def _validate_suite_and_scenarios(self) -> EvaluationReference:
        manifest = resolve_bench_suite_manifest(self.suite_id)
        if manifest is None:
            supported = get_supported_bench_suite_ids()
            raise ValueError(
                f"Unsupported evaluation suite '{self.suite_id}'. "
                f"Supported suites: {supported}."
            )
        if self.evaluation_version != manifest.evaluation_version:
            raise ValueError(
                f"Invalid evaluation_version '{self.evaluation_version}' for suite '{self.suite_id}'. "
                f"Expected '{manifest.evaluation_version}'."
            )
        if len(set(self.required_scenarios)) != len(self.required_scenarios):
            raise ValueError("Duplicate required scenario IDs.")
        valid_scenarios = set(manifest.scenario_ids)
        for scen in self.required_scenarios:
            if scen not in valid_scenarios:
                raise ValueError(
                    f"Unknown scenario ID '{scen}' for suite '{self.suite_id}'. "
                    f"Available scenarios: {sorted(list(valid_scenarios))}."
                )
        return self


class SuiteAggregateResult(BenchContract):
    passed: bool
    total_scenarios: int
    passed_scenarios: int
    score: float
    state: EvaluationState


class BenchEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
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
    evidence_format: Literal[1, 2] = 1
    state: EvaluationState = EvaluationState.UNVERIFIABLE
    quality_gate: Optional[QualityGateDecision] = None
    suite_aggregate: Optional[SuiteAggregateResult] = None
    evaluation_reference: Optional[EvaluationReference] = None
    output_contract: Optional[OutputContract] = None
    agent_tool_grants: List[str] = Field(default_factory=list)
    agent_forbidden_actions: List[str] = Field(default_factory=list)

    def evidence_payload(self, organization_id: str, project_id: str, evaluated_by: str) -> dict:
        result = self.model_dump(mode="json", exclude={"attestation"})
        if self.evidence_format == 1:
            for field in ("evidence_format", "state", "quality_gate", "output_contract",
                          "agent_tool_grants", "agent_forbidden_actions", "suite_aggregate", "evaluation_reference"):
                result.pop(field)
            for scenario in result["scenario_results"]:
                for field in ("scenario_version", "state", "execution", "grader_results"):
                    scenario.pop(field)
        return {"organization_id": organization_id, "project_id": project_id,
                "evaluated_by": evaluated_by, "result": result}


def resolve_bench_suite_manifest(identifier: str) -> Optional[BenchSuiteManifest]:
    from modules.bench.scenarios import get_bench_suite
    suite = get_bench_suite(identifier)
    if suite is None:
        return None
    return BenchSuiteManifest(**suite.model_dump(include={"suite_id", "evaluation_version", "aliases", "scenario_ids"}))


def get_supported_bench_suite_ids() -> List[str]:
    from modules.bench.scenarios import get_bench_suite_registry
    return get_bench_suite_registry().identifiers()
