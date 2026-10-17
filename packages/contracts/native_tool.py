"""Exact human-reviewed native action bindings; native skill text grants nothing."""
from typing import Any, Literal
from pydantic import Field

from packages.contracts.tool import ToolContract, ToolDeclaration
from packages.contracts.bench import evidence_hash


class NativeToolDefinition(ToolContract):
    connection_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    organization_id: str
    project_id: str
    owner_id: str
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    declaration: ToolDeclaration
    arguments: dict[str, Any]
    image_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    risk: Literal["HIGH_IMPACT"] = "HIGH_IMPACT"
    enabled: bool = True

    @property
    def capability(self):
        return "hermes.native." + self.tool_name

    @property
    def schema_hash(self):
        return evidence_hash(self.declaration.model_dump(mode="json"))


class NativeApproval(ToolContract):
    connection: NativeToolDefinition
    binding_id: str
    binding_hash: str
    observed_at: float
    expires_at: float
    approval_id: str
    attestation: str = ""

    def payload(self):
        return self.model_dump(mode="json", exclude={"attestation"})

    def configuration_hash(self):
        return evidence_hash({"connection": self.connection.model_dump(mode="json"), "binding_id": self.binding_id})


class NativeToolReview(ToolContract):
    connection_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    arguments: dict[str, Any]
    ttl_seconds: int = Field(default=60, ge=1, le=300)
