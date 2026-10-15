"""Read-only MCP contracts. Declarations and discovery confer no authority."""
from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.bench import OutputContract, evidence_hash, validate_output, validate_output_contract


PROTOCOL = "2025-11-25"


def loopback_endpoint(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
            or url.netloc != f"127.0.0.1:{url.port}" or url.path != "/mcp"
            or url.query or url.fragment or value != f"http://127.0.0.1:{url.port}/mcp"):
        raise ValueError("Only an explicitly approved literal loopback MCP endpoint is supported.")
    return value


def checked_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("type") != "object" or len(json.dumps(schema, allow_nan=False).encode()) > 12000:
        raise ValueError("MCP schemas must be bounded JSON objects.")
    validate_output_contract(OutputContract(format="json", strict=True, schema_definition=schema))
    return schema


def checked_data(value: Any, schema: dict[str, Any], limit: int = 16384):
    encoded = json.dumps(value, sort_keys=True, allow_nan=False)
    if len(encoded.encode()) > limit or validate_output(encoded,
            OutputContract(format="json", strict=True, schema_definition=schema))[0]:
        raise ValueError("MCP data does not satisfy the approved contract.")
    return value


class ToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False)


class ToolDeclaration(ToolContract):
    """Private Core-to-runtime proposal schema; contains no endpoint or credential."""
    name: str = Field(pattern=r"^aryn_mcp_[a-z0-9_]{1,48}$", max_length=64)
    input_schema: dict[str, Any]

    @model_validator(mode="after")
    def validate_schema(self):
        checked_schema(self.input_schema)
        if self.input_schema.get("additionalProperties") is not False or set(self.input_schema.get("properties", {})) & {
                "organization_id", "project_id", "server_id", "endpoint", "url", "headers", "authorization", "token", "credentials"}:
            raise ValueError("MCP proposal inputs cannot select scope, connection or authentication.")
        return self

    def definition(self):
        # Remote descriptions, titles and examples never become model instructions.
        def plain(value):
            if isinstance(value, dict):
                result = {}
                for key, child in value.items():
                    if key in {"description", "title", "examples", "default"}:
                        continue
                    if key in {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"} and isinstance(child, dict):
                        result[key] = {name: plain(schema) for name, schema in child.items()}
                    elif key in {"items", "additionalProperties", "unevaluatedProperties", "contains", "not", "if", "then", "else", "propertyNames", "allOf", "anyOf", "oneOf", "prefixItems"}:
                        result[key] = plain(child)
                    else:
                        result[key] = child
                return result
            if isinstance(value, list):
                return [plain(v) for v in value]
            return value
        return {"type": "function", "function": {"name": self.name,
            "description": "Read data using the explicitly approved project-scoped Core tool.",
            "parameters": plain(self.input_schema)}}


class MCPServerDefinition(ToolContract):
    server_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    organization_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    project_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    owner_id: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(max_length=128)
    transport: Literal["streamable_http"] = "streamable_http"
    profile: Literal["loopback_stateless_json"] = "loopback_stateless_json"
    server_name: str = Field(min_length=1, max_length=64)
    server_version: str = Field(min_length=1, max_length=32)
    enabled: bool = True
    tool_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    declaration: ToolDeclaration
    output_schema: dict[str, Any]
    risk: Literal["READ_ONLY", "REVERSIBLE", "HIGH_IMPACT", "BLOCKED"] = "READ_ONLY"
    timeout_seconds: float = Field(default=3, ge=0.05, le=5)
    max_response_bytes: int = Field(default=16384, ge=512, le=32768, strict=True)
    calls_per_minute: int = Field(default=12, ge=1, le=12, strict=True)

    @model_validator(mode="after")
    def confined_profile(self):
        loopback_endpoint(self.endpoint)
        checked_schema(self.output_schema)
        properties = self.output_schema.get("properties", {})
        if (not {"organization_id", "project_id"}.issubset(self.output_schema.get("required", []))
                or properties.get("organization_id", {}).get("const") != self.organization_id
                or properties.get("project_id", {}).get("const") != self.project_id
                or self.output_schema.get("additionalProperties") is not False):
            raise ValueError("The local MCP profile requires exact scoped structured output.")
        return self

    @property
    def capability(self):
        return f"aryn.mcp.{self.server_id}.{self.tool_name}.read"

    @property
    def schema_hash(self):
        return evidence_hash({"name": self.tool_name, "input": self.declaration.input_schema, "output": self.output_schema})


class MCPApproval(ToolContract):
    server: MCPServerDefinition
    binding_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    connection_identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: float
    expires_at: float
    protocol: Literal["2025-11-25"] = PROTOCOL
    attestation: str = ""

    def payload(self):
        return self.model_dump(mode="json", exclude={"attestation"})

    def configuration_hash(self):
        return evidence_hash({"server": self.server.model_dump(mode="json"), "binding_id": self.binding_id,
            "connection_identity": self.connection_identity})


class MCPInvocation(ToolContract):
    run_id: str = Field(pattern=r"^run_[a-f0-9]{32}$")
    organization_id: str
    project_id: str
    deadline_at: float
    call_number: int = Field(ge=1, le=2, strict=True)
    call_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    attestation: str = ""

    def payload(self):
        return self.model_dump(mode="json", exclude={"attestation"})


class MCPResultEvidence(ToolContract):
    run_id: str
    call_id: str
    organization_id: str
    project_id: str
    server_id: str
    server_name: str
    server_version: str
    remote_tool: str
    binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    endpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol: Literal["2025-11-25"]
    source: Literal["authenticated_loopback_mcp"]
    protocol_request_id: int | str
    network_requests: int = Field(ge=1, le=8, strict=True)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    result_bytes: int = Field(ge=0, le=32768, strict=True)
    duration_seconds: float = Field(ge=0)
