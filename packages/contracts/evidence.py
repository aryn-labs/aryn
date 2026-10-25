"""Trusted local evidence bindings and scoped browser selections."""

from typing import Literal
from pydantic import Field, model_validator
from packages.contracts.intelligence import Contract, Record, Identifier, Digest


class EvidenceBinding(Contract):
    binding_id: Identifier
    organization_id: Identifier
    project_id: Identifier
    kind: Literal["file", "git"]
    root: str = Field(min_length=1, max_length=1024)
    files: dict[Identifier, str] = Field(min_length=1, max_length=64)


class EvidenceBindings(Contract):
    schema_version: Literal[1] = 1
    bindings: list[EvidenceBinding] = Field(max_length=16)

    @model_validator(mode="after")
    def unique(self):
        if len({item.binding_id for item in self.bindings}) != len(self.bindings):
            raise ValueError("Evidence binding IDs must be unique.")
        return self


class RegisterEvidenceConnection(Contract):
    binding_id: Identifier
    name: str = Field(min_length=1, max_length=100)


class EvidenceConnection(Record):
    binding_id: Identifier
    binding_hash: Digest
    configuration_hash: Digest
    name: str
    kind: Literal["file", "git"]
    enabled: bool = Field(strict=True)
    revision: int = Field(strict=True, ge=1)
    file_keys: list[Identifier]


class EvidenceConnectionGrant(Contract):
    expected_configuration_hash: Digest
    enabled: bool = Field(strict=True)


class CollectEvidence(Contract):
    connection_id: Identifier
    file_key: Identifier
    title: str = Field(min_length=1, max_length=160)
    git_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    max_age_seconds: int = Field(default=86400, strict=True, ge=1, le=604800)


class EvidenceReference(Record):
    connection_id: Identifier
    binding_hash: Digest
    configuration_hash: Digest
    kind: Literal["file", "git"]
    file_key: Identifier
    git_revision: str | None


class InterpretBundle(Contract):
    assignment_id: Identifier
    allow_remote_model: Literal[True]
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")


class BriefInterpretation(Record):
    bundle_id: Identifier
    bundle_digest: Digest
    core_run_id: Identifier
    evaluation_digest: Digest
    evidence_status: str
    text: str = Field(max_length=16000)
    classification: Literal["model_interpretation"] = "model_interpretation"
    authority: Literal["informational_only"] = "informational_only"
    digest: Digest
