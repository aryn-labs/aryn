"""Domain contracts for Agent Factory.

Defines schemas for AgentDefinition, AgentBlueprint, AgentVersion, AgentAssignment,
and first-class typed policies: OutputContract, Constraints, ToolPolicy, ModelPolicy,
BudgetPolicy, and EvaluationReference.
Enforces immutable versioning, canonical payload hash computation, explicit tool grants,
deny-by-default execution, and tenant scoping.
Complies with ARYN-ARCH-001 Section 04 and AGENTS.md rules 3, 4, 5, 7.
"""

from __future__ import annotations

import datetime
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.bench import (
    OutputContract as AgentOutputContract,
    EvaluationReference as AgentEvaluationReference,
)


class VersionIntegrityError(ValueError):
    """Stored configuration does not match its canonical hash."""


class RollbackIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, revalidate_instances="always")
    target_version_id: str = Field(min_length=1, max_length=64)
    expected_current_version_id: str = Field(min_length=1, max_length=64)
    expected_transition_id: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(min_length=5, max_length=2000)
    idempotency_key: str = Field(min_length=16, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class PublicationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0.0"] = "1.0.0"
    publication_id: str
    organization_id: str
    project_id: str
    blueprint_id: str
    version_id: str
    payload_hash: str
    evaluation_id: str
    evaluation_hash: str
    approval_id: str
    approval_hash: str
    baseline_id: str
    baseline_hash: str
    comparison_id: Optional[str] = None
    comparison_hash: Optional[str] = None
    published_by: str
    published_at: str
    attestation: str = ""


class VersionRegistryEntry(BaseModel):
    version_id: str
    blueprint_id: str
    version_number: str
    status: str
    payload_hash: str
    created_at: str
    published_at: Optional[str] = None
    published_by: Optional[str] = None
    evaluation_id: Optional[str] = None
    bench_verified: bool = False
    bench_passed: bool = False
    approval_id: Optional[str] = None
    approval_status: Optional[str] = None
    baseline_id: Optional[str] = None
    publication_id: Optional[str] = None
    regression_comparison_id: Optional[str] = None
    current_baseline: bool = False
    active_assignment_count: int = 0
    rollback_eligible: bool = False
    reason: str = "publication_not_verified"
    limitations: List[str] = Field(default_factory=list)


class AssignmentTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0.0"] = "1.0.0"
    transition_id: str
    organization_id: str
    project_id: str
    assignment_id: str
    blueprint_id: str
    generation: int = Field(ge=1)
    from_version_id: Optional[str] = None
    to_version_id: str
    transition_type: Literal["initial", "adoption", "rollback"]
    actor_id: str
    reason: str
    requested_at: str
    committed_at: str
    idempotency_key: Optional[str] = None
    request_hash: str
    previous_transition_id: Optional[str] = None
    previous_hash: Optional[str] = None
    publication_reference: Dict[str, Any]
    assignment_hash: str
    attestation: str = ""


class ForbiddenToolError(ValueError):
    """Raised when an agent version requests unsafe or unauthorized tools."""


class AgentVersionStatus(str, Enum):
    DRAFT = "draft"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class AgentConstraints(BaseModel):
    """Operational constraints, abstention boundaries, and safety invariants."""
    disallowed_actions: List[str] = Field(default_factory=list)
    operational_rules: List[str] = Field(default_factory=list)
    require_evidence_citation: bool = True
    max_execution_time_seconds: int = Field(default=120, ge=1, le=3600)


class AgentToolPolicy(BaseModel):
    """Explicit tool grant policy enforcing deny-by-default boundaries (AGENTS.md rule 5)."""
    tool_grants: List[str] = Field(default_factory=list)
    forbidden_tools: List[str] = Field(
        default_factory=lambda: [
            "terminal",
            "file",
            "browser",
            "code_execution",
            "bash",
            "shell",
            "os_exec",
        ]
    )
    deny_by_default: bool = True
    network_access: bool = False
    file_write_access: bool = False
    code_execution: bool = False

    def is_tool_allowed(self, tool_name: str) -> bool:
        norm = tool_name.strip().lower()
        if any(norm == f.lower() for f in self.forbidden_tools):
            return False
        if norm in [t.lower() for t in self.tool_grants]:
            return True
        return not self.deny_by_default

    def validate_tool_grants(self) -> None:
        for tool in self.tool_grants:
            if any(tool.strip().lower() == f.lower() for f in self.forbidden_tools):
                raise ForbiddenToolError(
                    f"Requested tool '{tool}' is strictly forbidden by ARYN security policy (AGENTS.md rule 5)."
                )


class AgentModelPolicy(BaseModel):
    """Model policy enforcing exact model selection and prohibiting silent fallback (ADR-005)."""
    primary_model: str = "mock-fast"
    provider: str = "9router"
    allowed_models: List[str] = Field(default_factory=list)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    allow_fallback: bool = False
    stop_sequences: List[str] = Field(default_factory=list)

    def validate_model(self, requested_model: str) -> None:
        if requested_model == self.primary_model:
            return
        if self.allowed_models and requested_model in self.allowed_models:
            return
        raise ValueError(
            f"Model '{requested_model}' violates AgentModelPolicy: primary model is '{self.primary_model}' "
            f"and silent fallback is prohibited."
        )


class AgentBudgetPolicy(BaseModel):
    """Execution budget limits per run compliant with Core usage governance."""
    max_tokens_per_run: int = Field(default=4096, ge=1, le=100000)
    max_turns: int = Field(default=10, ge=1, le=100)
    max_cost_usd: float = Field(default=0.50, ge=0.0)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


class AgentDefinition(BaseModel):
    """Canonical, versioned specification of an ARYN agent persona and execution contract."""
    schema_version: str = "1.0.0"
    role: str = "general_agent"
    objective: str = ""
    owner: str = ""
    output_contract: AgentOutputContract = Field(default_factory=AgentOutputContract)
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    tool_policy: AgentToolPolicy = Field(default_factory=AgentToolPolicy)
    model_policy: AgentModelPolicy = Field(default_factory=AgentModelPolicy)
    budget_policy: AgentBudgetPolicy = Field(default_factory=AgentBudgetPolicy)
    evaluation_reference: AgentEvaluationReference = Field(default_factory=AgentEvaluationReference)


class AgentBlueprint(BaseModel):
    """The root specification for an agent persona."""
    id: str
    organization_id: str
    project_id: str
    name: str
    slug: str
    description: Optional[str] = None
    role: Optional[str] = None
    objective: Optional[str] = None
    owner: Optional[str] = None
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    @classmethod
    def from_stored(cls, row: Any) -> AgentBlueprint:
        return cls(
            id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            name=row.name,
            slug=row.slug,
            description=row.description,
            role=getattr(row, "role", None),
            objective=getattr(row, "objective", None),
            owner=getattr(row, "owner", None),
            created_by=row.created_by,
            created_at=row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else str(row.created_at),
            updated_at=row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else str(row.updated_at),
        )


class AgentVersion(BaseModel):
    """An immutable, versioned configuration of an agent."""
    id: str
    blueprint_id: str
    version_number: str
    status: AgentVersionStatus = AgentVersionStatus.DRAFT
    system_prompt: str
    model: str
    tool_grants: List[str] = Field(default_factory=list)
    temperature: float = Field(default=0.7, ge=0, le=2, allow_inf_nan=False)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    evaluation_id: Optional[str] = None
    published_at: Optional[str] = None
    published_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    # First-class typed domain contracts
    schema_version: str = "1.0.0"
    role: str = "general_agent"
    objective: str = ""
    owner: Optional[str] = None
    output_contract: AgentOutputContract = Field(default_factory=AgentOutputContract)
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    tool_policy: AgentToolPolicy = Field(default_factory=AgentToolPolicy)
    model_policy: AgentModelPolicy = Field(default_factory=AgentModelPolicy)
    budget_policy: AgentBudgetPolicy = Field(default_factory=AgentBudgetPolicy)
    evaluation_reference: AgentEvaluationReference = Field(default_factory=AgentEvaluationReference)

    @model_validator(mode="before")
    @classmethod
    def _synchronize_policies_and_scalars(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # If composite definition is supplied, extract its fields
        defn = data.get("definition")
        if isinstance(defn, AgentDefinition):
            defn_dict = defn.model_dump()
            for k, v in defn_dict.items():
                data.setdefault(k, v)
        elif isinstance(defn, dict):
            for k, v in defn.items():
                data.setdefault(k, v)

        # Sync model_policy with model, temperature, max_tokens
        model = data.get("model")
        temp = data.get("temperature", 0.7)
        mtok = data.get("max_tokens", 2048)
        mp = data.get("model_policy")
        if mp is None:
            if model:
                data["model_policy"] = AgentModelPolicy(
                    primary_model=model,
                    temperature=temp if temp is not None else 0.7,
                    max_tokens=mtok if mtok is not None else 2048,
                ).model_dump()
        else:
            if isinstance(mp, AgentModelPolicy):
                if not model:
                    data["model"] = mp.primary_model
                if "temperature" not in data or data["temperature"] is None:
                    data["temperature"] = mp.temperature
                if "max_tokens" not in data or data["max_tokens"] is None:
                    data["max_tokens"] = mp.max_tokens
            elif isinstance(mp, dict):
                if not model:
                    data["model"] = mp.get("primary_model", "mock-fast")
                if "temperature" not in data or data["temperature"] is None:
                    data["temperature"] = mp.get("temperature", 0.7)
                if "max_tokens" not in data or data["max_tokens"] is None:
                    data["max_tokens"] = mp.get("max_tokens", 2048)

        # Sync tool_policy with tool_grants
        tg = data.get("tool_grants")
        tp = data.get("tool_policy")
        if tp is None:
            if tg is not None:
                data["tool_policy"] = AgentToolPolicy(tool_grants=sorted(tg)).model_dump()
        else:
            if isinstance(tp, AgentToolPolicy):
                if tg is None:
                    data["tool_grants"] = sorted(tp.tool_grants)
            elif isinstance(tp, dict):
                if tg is None:
                    data["tool_grants"] = sorted(tp.get("tool_grants", []))

        # Output contract conversion if dict passed
        oc = data.get("output_contract")
        if isinstance(oc, dict):
            data["output_contract"] = AgentOutputContract.model_validate(oc)

        # Constraints conversion if list or dict passed
        c = data.get("constraints")
        if isinstance(c, list):
            data["constraints"] = AgentConstraints(operational_rules=c)
        elif isinstance(c, dict):
            data["constraints"] = AgentConstraints.model_validate(c)

        # Budget policy conversion if dict passed
        bp = data.get("budget_policy")
        if isinstance(bp, dict):
            data["budget_policy"] = AgentBudgetPolicy.model_validate(bp)

        # Evaluation reference conversion if dict passed
        er = data.get("evaluation_reference")
        if isinstance(er, dict):
            data["evaluation_reference"] = AgentEvaluationReference.model_validate(er)

        return data

    @property
    def definition(self) -> AgentDefinition:
        """Returns the typed AgentDefinition projection."""
        return AgentDefinition(
            schema_version=self.schema_version,
            role=self.role,
            objective=self.objective,
            owner=self.owner or "",
            output_contract=self.output_contract,
            constraints=self.constraints,
            tool_policy=self.tool_policy,
            model_policy=self.model_policy,
            budget_policy=self.budget_policy,
            evaluation_reference=self.evaluation_reference,
        )

    def canonical_payload(self) -> str:
        """Canonical version 3 payload including all first-class typed policies and metadata."""
        canonical = {
            "canonical_format": 3,
            "id": self.id,
            "blueprint_id": self.blueprint_id,
            "version_number": self.version_number,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "tool_grants": sorted(self.tool_grants),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
            "role": self.role,
            "objective": self.objective,
            "owner": self.owner or "",
            "output_contract": self.output_contract.model_dump(mode="json"),
            "constraints": self.constraints.model_dump(mode="json"),
            "tool_policy": self.tool_policy.model_dump(mode="json"),
            "model_policy": self.model_policy.model_dump(mode="json"),
            "budget_policy": self.budget_policy.model_dump(mode="json"),
            "evaluation_reference": self.evaluation_reference.model_dump(mode="json"),
        }
        return json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def calculate_payload_hash(self) -> str:
        encoded = self.canonical_payload().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def canonical_payload_legacy_v2(self) -> str:
        """Legacy version 2 payload for backwards-compatible integrity verification."""
        canonical = {
            "canonical_format": 2,
            "id": self.id,
            "blueprint_id": self.blueprint_id,
            "version_number": self.version_number,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "tool_grants": sorted(self.tool_grants),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "metadata": self.metadata,
        }
        return json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def calculate_legacy_v2_payload_hash(self) -> str:
        encoded = self.canonical_payload_legacy_v2().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _has_custom_definition_fields(self) -> bool:
        """Returns True if any first-class definition field differs from clean legacy defaults."""
        if self.role != "general_agent":
            return True
        if self.objective != "":
            return True
        if self.owner is not None:
            return True
        if self.schema_version != "1.0.0":
            return True
        if self.output_contract != AgentOutputContract():
            return True
        if self.constraints != AgentConstraints():
            return True
        if self.tool_policy != AgentToolPolicy(tool_grants=sorted(self.tool_grants)):
            return True
        if self.model_policy != AgentModelPolicy(
            primary_model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            return True
        if self.budget_policy != AgentBudgetPolicy():
            return True
        if self.evaluation_reference != AgentEvaluationReference():
            return True
        return False

    @property
    def canonical_format(self) -> int:
        """Returns 3 for current canonical format, 2 for un-tampered legacy format, 0 if invalid."""
        if not self.payload_hash:
            return 0
        if self.payload_hash == self.calculate_payload_hash():
            return 3
        if self.payload_hash == self.calculate_legacy_v2_payload_hash() and not self._has_custom_definition_fields():
            return 2
        return 0

    def verify_integrity(self, require_canonical: bool = False) -> None:
        if not self.payload_hash:
            raise VersionIntegrityError("Agent version integrity check failed: missing payload hash.")
        current_hash = self.calculate_payload_hash()
        if self.payload_hash == current_hash:
            return
        if require_canonical:
            raise VersionIntegrityError(
                "Agent version integrity check failed: active lifecycle operations require canonical format 3. "
                "Legacy payload formats cannot enter evaluation, approval, or publication; create a new version."
            )
        legacy_hash = self.calculate_legacy_v2_payload_hash()
        if self.payload_hash == legacy_hash:
            if self._has_custom_definition_fields():
                raise VersionIntegrityError(
                    "Agent version integrity check failed: custom definition contracts cannot be authenticated "
                    "under legacy payload format. Create a new version to authenticate first-class policies."
                )
            return
        raise VersionIntegrityError("Agent version integrity check failed; create and evaluate a new version.")

    @classmethod
    def from_stored(cls, row: Any) -> AgentVersion:
        try:
            output_contract_raw = getattr(row, "output_contract_json", "{}")
            constraints_raw = getattr(row, "constraints_json", "[]")
            tool_policy_raw = getattr(row, "tool_policy_json", "{}")
            model_policy_raw = getattr(row, "model_policy_json", "{}")
            budget_policy_raw = getattr(row, "budget_policy_json", "{}")
            eval_ref_raw = getattr(row, "evaluation_reference_json", "{}")

            output_contract = json.loads(output_contract_raw or "{}")
            constraints = json.loads(constraints_raw or "[]")
            tool_policy = json.loads(tool_policy_raw or "{}")
            model_policy = json.loads(model_policy_raw or "{}")
            budget_policy = json.loads(budget_policy_raw or "{}")
            eval_ref = json.loads(eval_ref_raw or "{}")

            tool_grants = json.loads(row.tool_grants_json) if row.tool_grants_json else []
            metadata = json.loads(row.metadata_json) if row.metadata_json else {}

            version = cls(
                id=row.id,
                blueprint_id=row.blueprint_id,
                version_number=row.version_number,
                status=row.status,
                system_prompt=row.system_prompt,
                model=row.model,
                tool_grants=tool_grants,
                temperature=row.temperature,
                max_tokens=row.max_tokens,
                metadata=metadata,
                payload_hash=row.payload_hash,
                evaluation_id=row.evaluation_id,
                published_at=row.published_at.isoformat() if row.published_at else None,
                published_by=row.published_by,
                created_at=row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else str(row.created_at),
                schema_version=getattr(row, "schema_version", "1.0.0") or "1.0.0",
                role=getattr(row, "role", "general_agent") or "general_agent",
                objective=getattr(row, "objective", "") or "",
                owner=getattr(row, "owner", None),
                output_contract=AgentOutputContract.model_validate(output_contract) if output_contract else AgentOutputContract(),
                constraints=AgentConstraints.model_validate(constraints) if isinstance(constraints, dict) and constraints else (
                    AgentConstraints(operational_rules=constraints) if isinstance(constraints, list) and constraints else AgentConstraints()
                ),
                tool_policy=AgentToolPolicy.model_validate(tool_policy) if tool_policy else AgentToolPolicy(tool_grants=tool_grants),
                model_policy=AgentModelPolicy.model_validate(model_policy) if model_policy else AgentModelPolicy(
                    primary_model=row.model,
                    temperature=row.temperature,
                    max_tokens=row.max_tokens,
                ),
                budget_policy=AgentBudgetPolicy.model_validate(budget_policy) if budget_policy else AgentBudgetPolicy(),
                evaluation_reference=AgentEvaluationReference.model_validate(eval_ref) if eval_ref else AgentEvaluationReference(),
            )
            version.verify_integrity()
            return version
        except (ValueError, TypeError) as exc:
            if isinstance(exc, VersionIntegrityError):
                raise
            raise VersionIntegrityError("Stored agent version integrity check failed.") from exc


class AgentAssignment(BaseModel):
    """Binds a published AgentVersion to an operational scope (project and optional division)."""
    id: str
    organization_id: str
    project_id: str
    division_id: Optional[str] = None
    blueprint_id: str
    version_id: str
    current_transition_id: Optional[str] = None
    role_name: str
    status: str = "active"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
