"""Bounded Studio read contracts and scoped division editing inputs."""
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class DivisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(default="", max_length=2000)


class DivisionUpdate(DivisionInput):
    expected_generation: int = Field(ge=1)


class ResourceItem(BaseModel):
    id: str
    organization_id: str
    project_id: str
    name: str
    created_at: str
    status: str | None = None
    slug: str | None = None
    description: str | None = None
    generation: int | None = None
    verified: bool | None = None
    verification_reason: str | None = None
    references: dict[str, Any] = Field(default_factory=dict)


T = TypeVar("T")


class ResourcePage(BaseModel, Generic[T]):
    organization_id: str
    project_id: str
    resource: str
    items: list[T]
    next_cursor: str | None
    limit: int
    refreshed_at: str


class Metric(BaseModel):
    value: int | None
    definition: str
    source: str
    verification: Literal["recorded_inventory", "verified_bounded", "unavailable"] = "recorded_inventory"


class Attention(BaseModel):
    code: str
    count: int
    description: str
    route: str


class WorkspaceSummary(BaseModel):
    organization_id: str
    project_id: str
    refreshed_at: str
    metrics: dict[str, Metric]
    permissions: dict[str, bool]
    attention: list[Attention]
    latest_runs: list[ResourceItem]
    latest_audits: list[ResourceItem]
    review_candidates: list[ResourceItem]
    budget: dict[str, Any] | None
    usage: dict[str, Any]
