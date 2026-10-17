"""Typed runtime control plane. Discovery is evidence, never a permission grant."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ControlContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False)


class RuntimeFeature(ControlContract):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    tools: list[str] = Field(default_factory=list, max_length=1024)
    availability: Literal["available", "unavailable", "unknown"] = "unknown"
    configuration_readiness: Literal["ready", "missing_dependencies", "unknown"] = "unknown"
    risk: Literal["read", "filesystem", "execution", "network", "persistent_state", "secret", "external_write", "delegation", "unknown"] = "unknown"
    required_permissions: list[str] = Field(default_factory=lambda: ["tool:register", "run:create"])
    execution_environment: Literal["core", "isolated_worker", "unavailable"] = "unavailable"
    approval_required: bool = True
    enabled: bool = False
    executable: bool = False
    verification: Literal["installed_source", "runtime_observed", "offline_verified", "unverified"] = "unverified"
    reason: str = "runtime_evidence_unavailable"
    native_api: bool = False
    native_cli: bool = False


class RuntimeSkill(ControlContract):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=128)
    content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    enabled: bool = False
    source_verified: bool = False


class SkillRead(ControlContract):
    name: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SkillContent(SkillRead):
    content: str = Field(max_length=65536)


class RuntimeInventory(ControlContract):
    schema_version: Literal[1] = 1
    runtime: Literal["Hermes"] = "Hermes"
    version: str = Field(default="unknown", max_length=128)
    source_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    configuration_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    toolsets: list[RuntimeFeature] = Field(default_factory=list, max_length=2048)
    features: list[RuntimeFeature] = Field(default_factory=list, max_length=128)
    skills: list[RuntimeSkill] = Field(default_factory=list, max_length=4096)
    settings: dict[str, str | int | bool] = Field(default_factory=dict)
    reason: str = "runtime_inventory_unavailable"


class SkillAssignment(ControlContract):
    name: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RuntimePolicy(ControlContract):
    """Stored in existing canonical AgentVersion metadata; never changes old hashes."""
    skills: list[SkillAssignment] = Field(default_factory=list, max_length=64)
    toolsets: list[str] = Field(default_factory=list, max_length=128)
    environment: Literal["confined", "isolated_worker"] = "confined"
    require_approval: Literal[True] = True
    memory: bool = False
    delegation: bool = False
    scheduling: bool = False
    max_child_executions: int = Field(default=0, ge=0, le=32)

    @model_validator(mode="after")
    def unique_names(self):
        if len({s.name for s in self.skills}) != len(self.skills) or len(set(self.toolsets)) != len(self.toolsets):
            raise ValueError("Runtime capability assignments must be unique.")
        if any(not name or len(name) > 128 for name in self.toolsets):
            raise ValueError("Invalid toolset identity.")
        return self


class GatewayConnectionChange(ControlContract):
    base_url: str = Field(max_length=512)
    api_key: SecretStr = Field(exclude=True, repr=False)
    expected_configuration_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class GatewayConnectionRevoke(ControlContract):
    expected_configuration_id: str = Field(pattern=r"^[a-f0-9]{64}$")
