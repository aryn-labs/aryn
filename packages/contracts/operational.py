"""Typed disposable targets. Browser requests contain registry IDs, never paths."""

from typing import Literal
from pydantic import Field, model_validator
from packages.contracts.intelligence import (
    Contract, Identifier, Digest, DemoFixture, DemoObservation, DemoState,
    ActionProposal, RecoveryContract, RecoveryExecution, RecoveryVerification, Record, CapsuleReplay,
)


class TargetBinding(Contract):
    binding_id: Identifier
    environment_id: Identifier
    organization_id: Identifier
    project_id: Identifier
    container_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    profile: dict

    @model_validator(mode="after")
    def isolated(self):
        if self.profile != {"network": "none", "read_only_root": True, "user": "65532:65532",
                "memory_bytes": 134217728, "nano_cpus": 500000000, "pids": 64}:
            raise ValueError("Operational target profile differs.")
        return self


class OperationalBindings(Contract):
    schema_version: Literal[1] = 1
    targets: list[TargetBinding] = Field(max_length=16)

    @model_validator(mode="after")
    def unique(self):
        if len({item.binding_id for item in self.targets}) != len(self.targets):
            raise ValueError("Operational binding IDs must be unique.")
        if (len({item.container_id for item in self.targets}) != len(self.targets)
                or len({item.environment_id for item in self.targets}) != len(self.targets)):
            raise ValueError("A physical operational target cannot have multiple binding aliases.")
        return self


class RegisterTarget(Contract):
    binding_id: Identifier
    name: str = Field(min_length=1, max_length=100)


class TargetGrant(Contract):
    enabled: bool = Field(strict=True)
    expected_configuration_hash: Digest


class ControllerState(Contract):
    instance: str = Field(pattern=r"^[a-f0-9]{32}$")
    generation: int = Field(strict=True, ge=1)
    running: bool = Field(strict=True)
    blocking_fault: bool = Field(strict=True)
    child_instance: Identifier
    last_execution_id: Identifier | None
    expires_at: float = Field(gt=0)


class BusinessHealth(Contract):
    instance: Identifier
    healthy: bool = Field(strict=True)
    requests: int = Field(strict=True, ge=0)


class ServiceProbe(Contract):
    controller_status: Literal[200]
    controller: ControllerState
    business_status: Literal[200, 503] | None
    business: BusinessHealth | None
    business_available: bool = Field(strict=True)
    healthy: bool = Field(strict=True)
    observed_at: float = Field(gt=0)
    latency_ms: float = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def measured_health(self):
        if self.business_available != (self.business is not None and self.business_status is not None):
            raise ValueError("Business response availability differs.")
        expected = bool(self.business_available and self.business_status == 200
            and self.business.healthy and self.controller.running
            and self.business.instance == self.controller.child_instance)
        if self.healthy != expected:
            raise ValueError("Observed health is inconsistent.")
        return self


class ServiceTarget(DemoFixture):
    target_kind: Literal["isolated_service"] = "isolated_service"
    binding_id: Identifier
    binding_hash: Digest
    instance: str = Field(pattern=r"^[a-f0-9]{32}$")
    enabled: bool = Field(strict=True)
    configuration_hash: Digest
    configuration_revision: int = Field(strict=True, ge=1)
    max_actions_per_hour: Literal[6] = 6
    timeout_seconds: Literal[15] = 15
    probe: ServiceProbe
    last_admission_id: Identifier | None = None


class ServiceObservation(DemoObservation):
    target_kind: Literal["isolated_service"] = "isolated_service"
    reason: Literal["created", "collection", "verification"]
    binding_hash: Digest
    configuration_hash: Digest
    probe: ServiceProbe


class ServiceState(DemoState):
    instance: str = Field(pattern=r"^[a-f0-9]{32}$")
    generation: int = Field(strict=True, ge=1)
    child_instance: Identifier
    last_execution_id: Identifier | None
    probe_digest: Digest


class ServiceHealthContract(RecoveryContract):
    kind: Literal["isolated_service_health"] = "isolated_service_health"


class CompensationPlan(Contract):
    supported: Literal[False] = False
    reason: Literal["Stopping a recovered process could discard new work; operator review is required."] = "Stopping a recovered process could discard new work; operator review is required."


class ServiceProposal(ActionProposal):
    action: Literal["restart_service"] = "restart_service"
    reversible_intent: Literal["start_stopped_disposable_business_process"] = "start_stopped_disposable_business_process"
    preconditions: Literal["verified_isolated_service_stopped_at_exact_generation"] = "verified_isolated_service_stopped_at_exact_generation"
    verification: ServiceHealthContract = Field(default_factory=ServiceHealthContract)
    binding_hash: Digest
    configuration_hash: Digest
    instance: str = Field(pattern=r"^[a-f0-9]{32}$")
    expires_at: float = Field(gt=0)
    timeout_seconds: Literal[15] = 15
    risk: Literal["HIGH_IMPACT"] = "HIGH_IMPACT"
    expected_impact: Literal["Start one stopped disposable business process within its existing isolation profile."] = "Start one stopped disposable business process within its existing isolation profile."
    approval_required: Literal[True] = True
    compensation: CompensationPlan = Field(default_factory=CompensationPlan)
    execution_profile: dict


class ServiceExecution(RecoveryExecution):
    before_snapshot: ServiceState
    deadline_at: float = Field(gt=0)
    admission: dict
    action_receipt: dict | None = None
    previous_admission_id: Identifier | None = None


class ServiceCapsule(Record):
    incident_id: Identifier
    incident_revision: int = Field(strict=True, ge=1)
    bundle_id: Identifier
    bundle_digest: Digest
    proposal_id: Identifier
    proposal_hash: Digest
    verification_id: Identifier | None
    outcome: Literal["RECOVERED", "DEGRADED", "OUTCOME_UNKNOWN"]
    recovered: bool | None
    failure_reason: str | None
    scenario_id: Identifier = "isolated_service_recovery"
    scenario_version: Literal["1.0.0"] = "1.0.0"
    snapshot: ServiceState
    target_kind: Literal["isolated_service"] = "isolated_service"
    lineage: dict
    evidence: list[dict] = Field(max_length=16)
    scenario_candidate: dict
    sanitized: Literal[True] = True
    digest: Digest


class ServiceReplay(CapsuleReplay):
    source_outcome: Literal["RECOVERED", "DEGRADED", "OUTCOME_UNKNOWN"]


class ServiceVerification(RecoveryVerification):
    contract: ServiceHealthContract


def service_target(value):
    return value.get("target_kind") == "isolated_service"
