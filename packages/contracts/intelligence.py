"""Scoped evidence and disposable incident recovery contracts.

No request can provide actor identity, a command, a URL or a host path.
"""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Revision = Annotated[int, Field(strict=True, ge=1)]
EvidenceStatus = Literal[
    "SUPPORTED", "CONFLICTING", "INSUFFICIENT_EVIDENCE", "NOT_FOUND"
]
IncidentStatus = Literal[
    "OPEN",
    "INVESTIGATING",
    "PROPOSED",
    "EXECUTING",
    "DEGRADED",
    "RECOVERED",
    "CLOSED",
    "OUTCOME_UNKNOWN",
]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, validate_assignment=True
    )


class Record(Contract):
    id: Identifier
    organization_id: Identifier
    project_id: Identifier
    created_at: str


class SourceReference(Contract):
    kind: Literal["artifact", "run", "demo_observation", "document"]
    id: Identifier


class EvidenceSource(Record):
    title: str = Field(min_length=1, max_length=160)
    source_ref: SourceReference
    source_digest: Digest
    digest: Digest
    length: int = Field(strict=True, ge=0, le=65536)
    mime: Literal["application/json", "text/plain"]
    observed_at: str
    collected_at: str
    sanitized: bool
    quality: Literal["verified_internal_snapshot", "disposable_demo", "user_document"]
    max_age_seconds: int = Field(strict=True, ge=1, le=604800)


class EvidenceDocument(Record):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(max_length=16000)
    digest: Digest
    sanitized: bool
    demo: Literal[True] = True


class Hypothesis(Contract):
    question: str = Field(min_length=1, max_length=500)
    predicate: Literal["service_healthy", "contains_text", "run_completed"]
    text: str = Field(default="", max_length=200)
    minimum_sources: int = Field(default=1, strict=True, ge=1, le=8)
    target_id: Identifier | None = None

    @model_validator(mode="after")
    def typed_predicate(self):
        if (self.predicate == "contains_text") != bool(self.text.strip()):
            raise ValueError("Only contains_text requires a nonempty literal text.")
        if (self.predicate == "service_healthy") != (self.target_id is not None):
            raise ValueError(
                "Only service_healthy requires an exact disposable target ID."
            )
        return self


class EvidenceItem(Contract):
    source_id: Identifier
    relationship: Literal["support", "conflict", "neutral"]
    integrity: Literal["VERIFIED", "UNVERIFIED"]
    freshness: Literal["fresh", "stale", "unavailable"]
    observed_at: str | None = None
    collected_at: str | None = None
    excerpt: str = Field(default="", max_length=2000)
    reason: str


class EvidenceBundle(Record):
    title: str = Field(min_length=1, max_length=160)
    hypothesis: Hypothesis
    source_ids: list[Identifier] = Field(max_length=16)
    source_digests: dict[str, Digest]
    workflow_run_id: Identifier | None = None
    status: EvidenceStatus
    abstention: str | None
    digest: Digest


class EvidenceLink(Record):
    bundle_id: Identifier
    reference_kind: Literal[
        "run", "artifact", "workflow_run", "incident", "capsule", "replay"
    ]
    reference_id: Identifier


class IngestReference(Contract):
    source_ref: SourceReference
    title: str = Field(min_length=1, max_length=160)
    max_age_seconds: int = Field(default=86400, strict=True, ge=1, le=604800)


class CreateDocument(Contract):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=16000)


class CreateBundle(Contract):
    title: str = Field(min_length=1, max_length=160)
    hypothesis: Hypothesis
    source_ids: list[Identifier] = Field(default_factory=list, max_length=16)
    workflow_run_id: Identifier | None = None

    @model_validator(mode="after")
    def unique_sources(self):
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Evidence sources must be unique.")
        return self


class DemoState(Contract):
    running: bool = Field(strict=True)
    blocking_fault: bool = Field(strict=True)


class DemoFixture(Record):
    name: str = Field(min_length=1, max_length=100)
    disposable: Literal[True] = True
    revision: Revision
    running: bool = Field(strict=True)
    blocking_fault: bool = Field(strict=True)
    updated_at: str
    last_execution_id: Identifier | None = None


class DemoObservation(Record):
    target_id: Identifier
    target_revision: Revision
    running: bool
    blocking_fault: bool
    healthy: bool
    disposable: Literal[True] = True
    reason: Literal["created", "demo_change", "verification"]


class CreateFixture(Contract):
    name: str = Field(min_length=1, max_length=100)


class ChangeFixture(Contract):
    expected_revision: Revision
    running: bool = Field(strict=True)
    blocking_fault: bool = Field(strict=True)


class Signal(Record):
    target_id: Identifier
    source_id: Identifier
    dedup_key: str = Field(min_length=1, max_length=128)
    severity: Literal["low", "medium", "high"]
    demo: Literal[True] = True


class CollectSignal(Contract):
    target_id: Identifier
    dedup_key: str = Field(min_length=1, max_length=128)
    severity: Literal["low", "medium", "high"] = "medium"


class IncidentTimeline(Record):
    incident_id: Identifier
    sequence: Revision
    event: str
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    actor_id: Identifier
    reference_id: Identifier | None = None


class Incident(Record):
    title: str
    target_id: Identifier
    signal_id: Identifier
    dedup_key: str
    severity: Literal["low", "medium", "high"]
    owner_id: Identifier
    status: IncidentStatus
    revision: Revision
    bundle_id: Identifier | None = None
    proposal_id: Identifier | None = None
    execution_id: Identifier | None = None
    verification_id: Identifier | None = None
    capsule_id: Identifier | None = None
    updated_at: str
    demo: Literal[True] = True


class IncidentRevision(Contract):
    expected_revision: Revision


class InvestigateIncident(IncidentRevision):
    source_ids: list[Identifier] | None = Field(default=None, max_length=16)


class Investigation(Record):
    incident_id: Identifier
    bundle_id: Identifier
    readonly: Literal[True] = True
    diagnosis: Literal["ABSTAIN", "LATEST_DEMO_TELEMETRY_UNHEALTHY"]
    reason: str


class RecoveryContract(Contract):
    kind: Literal["demo_health_v1"] = "demo_health_v1"
    require_running: Literal[True] = True
    require_no_blocking_fault: Literal[True] = True


class ActionProposal(Record):
    incident_id: Identifier
    target_id: Identifier
    target_revision: Revision
    bundle_id: Identifier
    bundle_digest: Digest
    action: Literal["restart_demo"] = "restart_demo"
    parameters: dict[str, bool] = Field(default_factory=dict)
    reversible_intent: Literal["restore_prior_demo_running_state"] = (
        "restore_prior_demo_running_state"
    )
    preconditions: Literal["verified_disposable_target_unhealthy_at_exact_revision"] = (
        "verified_disposable_target_unhealthy_at_exact_revision"
    )
    verification: RecoveryContract = Field(default_factory=RecoveryContract)
    reason: str = Field(min_length=1, max_length=1000)
    payload_hash: Digest

    @model_validator(mode="after")
    def empty_parameters(self):
        if self.parameters:
            raise ValueError("restart_demo accepts no caller parameters.")
        return self


class ProposeAction(IncidentRevision):
    action: Literal["restart_demo"] = "restart_demo"
    target_id: Identifier
    target_revision: Revision
    bundle_id: Identifier
    reason: str = Field(min_length=1, max_length=1000)


class ApproveAction(Contract):
    payload_hash: Digest
    reason: str = Field(min_length=1, max_length=1000)


class ApprovalReference(Contract):
    approval_id: Identifier
    payload_hash: Digest
    approved_by: Identifier
    created_at: str


class ExecuteAction(Contract):
    proposal_id: Identifier
    payload_hash: Digest
    idempotency_key: str = Field(min_length=1, max_length=128)


class RecoveryExecution(Record):
    incident_id: Identifier
    proposal_id: Identifier
    payload_hash: Digest
    target_id: Identifier
    owner_id: str
    actor_id: Identifier
    idempotency_key: str
    approval: ApprovalReference
    status: Literal[
        "running",
        "action_completed",
        "verified",
        "health_failed",
        "denied",
        "outcome_unknown",
    ]
    before_revision: Revision
    before_snapshot: DemoState
    after_revision: Revision | None = None
    error_code: str | None = None


class RecoveryVerification(Record):
    incident_id: Identifier
    execution_id: Identifier
    target_id: Identifier
    observation_id: Identifier
    target_revision: Revision
    contract: RecoveryContract
    recovered: bool
    digest: Digest


class IncidentCapsule(Record):
    incident_id: Identifier
    bundle_id: Identifier
    bundle_digest: Digest
    proposal_id: Identifier
    proposal_hash: Digest
    verification_id: Identifier
    recovered: Literal[True] = True
    scenario_id: Identifier
    scenario_version: Literal["1.0.0"] = "1.0.0"
    snapshot: DemoState
    sanitized: Literal[True] = True
    digest: Digest


class CapsuleReplay(Record):
    capsule_id: Identifier
    capsule_digest: Digest
    scenario_id: Identifier
    scenario_version: Literal["1.0.0"] = "1.0.0"
    backend: Literal["deterministic_in_memory"] = "deterministic_in_memory"
    model: None = None
    provider: None = None
    passed: bool
    graders: list[dict]
    live_write_calls: Literal[0] = 0
    promotion_evidence: Literal[False] = False
    digest: Digest


class ReplayCapsule(Contract):
    """The server-owned scenario accepts no caller execution parameters."""
