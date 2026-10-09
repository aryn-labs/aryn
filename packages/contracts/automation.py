"""Core scheduling inputs contain no runtime, identity or host authority."""

from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, field_validator
from packages.contracts.intelligence import (
    Contract,
    Record,
    Identifier,
    Digest,
    Revision,
)


class Schedule(Contract):
    timezone: str = Field(default="UTC", max_length=100)
    kind: Literal["interval", "daily", "weekly"] = "daily"
    start_at: str
    interval_minutes: int = Field(default=60, strict=True, ge=1, le=10080)
    local_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7
    )

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone IANA tidak dikenal.") from exc
        return value

    @field_validator("start_at")
    @classmethod
    def aware_start(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("start_at memerlukan UTC offset.")
        return parsed.astimezone(timezone.utc).isoformat()

    @field_validator("weekdays")
    @classmethod
    def days(cls, value):
        if any(type(day) is not int or not 0 <= day <= 6 for day in value) or len(
            set(value)
        ) != len(value):
            raise ValueError("Hari harus unik, Senin=0 sampai Minggu=6.")
        return sorted(value)


class AutomationTarget(Contract):
    kind: Literal["agent", "workflow"]
    id: Identifier
    version_id: Identifier
    payload_hash: Digest
    activation_id: Identifier | None = None


class AutomationPolicy(Contract):
    overlap: Literal["skip", "queue"] = "skip"
    missed: Literal["skip", "catch_up"] = "skip"
    catch_up_limit: int = Field(default=1, strict=True, ge=1, le=3)
    max_runs_per_day: int = Field(default=24, strict=True, ge=1, le=100)
    max_tokens_per_task: int = Field(default=4096, strict=True, ge=128, le=32768)
    max_attempts: int = Field(default=1, strict=True, ge=1, le=3)
    backoff_seconds: int = Field(default=60, strict=True, ge=60, le=3600)


class AutomationInput(Contract):
    title: str = Field(min_length=1, max_length=160)
    target: AutomationTarget
    input: str = Field(min_length=1, max_length=8000)
    allow_remote_model: Literal[True]
    schedule: Schedule
    policy: AutomationPolicy = Field(default_factory=AutomationPolicy)
    expected_revision: Revision | None = None


class AutomationDefinition(Record):
    title: str
    owner_actor_id: Identifier
    revision: Revision
    configuration: AutomationInput
    payload_hash: Digest
    status: Literal["paused", "enabled"] = "paused"
    next_run_at: str
    last_occurrence_id: Identifier | None = None
    updated_at: str


OccurrenceStatus = Literal[
    "queued",
    "dispatching",
    "waiting_review",
    "completed",
    "failed",
    "outcome_unknown",
    "blocked",
    "skipped",
    "retry_wait",
    "reconciled",
]


class AutomationOccurrence(Record):
    automation_id: Identifier
    target_id: Identifier
    occurrence_key: str = Field(max_length=160)
    scheduled_at: str
    definition_revision: Revision
    payload_hash: Digest
    owner_id: str
    status: OccurrenceStatus
    attempts: int = 0
    retry_at: str | None = None
    run_id: Identifier | None = None
    run_kind: Literal["agent", "workflow"]
    error_code: str | None = None
    completed_at: str | None = None
    admitted_at: str | None = None


class AutomationEvent(Record):
    automation_id: Identifier
    occurrence_id: Identifier | None = None
    event: str
    actor_id: str
    details: dict = Field(default_factory=dict)


class AutomationDecision(Contract):
    expected_revision: Revision
    payload_hash: Digest
    reason: str = Field(min_length=5, max_length=500)


class AutomationStateInput(Contract):
    expected_revision: Revision
    enabled: bool = Field(strict=True)


class ManualOccurrence(Contract):
    expected_revision: Revision
    idempotency_key: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"
    )


class ReconcileOccurrence(Contract):
    reason: str = Field(min_length=5, max_length=500)
    acknowledge_no_retry: Literal[True]


class PreviewInput(Contract):
    schedule: Schedule


class Capability(Contract):
    namespace: str
    version: Literal["1"] = "1"
    adapter: str
    modes: list[Literal["local", "hosted"]]
    risk: Literal["read", "governed_text", "disposable_write", "privileged"]
    available: bool
    effective_permission: bool
    grants: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    missing_prerequisites: list[str] = Field(default_factory=list)
    disabled_reason: str | None = None


class CapabilityRegistry(Contract):
    organization_id: str
    project_id: str
    mode: Literal["local", "hosted"]
    checked_at: str
    capabilities: list[Capability]
    entitlement: Literal["unknown"] = "unknown"
    entitlement_reason: str = "Tidak ada sumber entitlement terverifikasi."
    billing_category: Literal["external_or_local"] = "external_or_local"
    provider_hard_cost_cap: Literal[False] = False
    scheduler_authority: Literal["core_single_owner"] = "core_single_owner"
    local_offline_execution: Literal[False] = False
