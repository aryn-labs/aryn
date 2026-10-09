"""Bounded graph language. No executable expressions or host capabilities."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Schema = Literal["text", "brief", "content", "website"]
Kind = Literal["start", "agent", "condition", "handoff", "review", "end"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Predicate(Strict):
    operator: Literal["contains", "equals", "nonempty"]
    literal: str = Field(default="", max_length=100)

    def matches(self, text: str) -> bool:
        if self.operator == "nonempty":
            return bool(text.strip())
        return (
            self.literal in text
            if self.operator == "contains"
            else text == self.literal
        )


class Node(Strict):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,47}$")
    label: str = Field(min_length=1, max_length=120)
    kind: Kind
    input_schema: Schema = "text"
    output_schema: Schema = "text"
    assignment_id: str | None = Field(default=None, max_length=64)
    agent_version_id: str | None = Field(default=None, max_length=64)
    renderer: Literal["static-document-v1"] | None = None
    predicate: Predicate | None = None

    @model_validator(mode="after")
    def capabilities(self):
        if self.kind == "agent":
            if self.renderer:
                if (
                    self.assignment_id
                    or self.agent_version_id
                    or (self.input_schema, self.output_schema) != ("content", "website")
                ):
                    raise ValueError(
                        "Static document renderer requires content to website and no runtime agent."
                    )
            elif (
                not self.assignment_id
                or not self.agent_version_id
                or self.output_schema == "website"
            ):
                raise ValueError(
                    "Agent task requires a pinned assignment/version and a text envelope output."
                )
        elif self.assignment_id or self.agent_version_id or self.renderer:
            raise ValueError("Only task nodes may declare an execution target.")
        if (self.kind == "condition") != (self.predicate is not None):
            raise ValueError("Only condition nodes require typed predicates.")
        if self.kind != "agent" and self.input_schema != self.output_schema:
            raise ValueError("Control and handoff nodes preserve their schema.")
        return self


class Edge(Strict):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,47}$")
    source: str = Field(max_length=48)
    target: str = Field(max_length=48)
    source_port: Literal["value", "yes", "no"] = "value"
    target_port: Literal["value"] = "value"


class Graph(Strict):
    nodes: list[Node] = Field(min_length=3, max_length=24)
    edges: list[Edge] = Field(min_length=2, max_length=32)


class Position(Strict):
    id: str = Field(max_length=48)
    x: float = Field(ge=-10000, le=10000)
    y: float = Field(ge=-10000, le=10000)


class WorkflowDefinition(Strict):
    name: str = Field(min_length=1, max_length=120)
    graph: Graph
    positions: list[Position] = Field(default_factory=list, max_length=24)


class SaveWorkflow(WorkflowDefinition):
    expected_revision: int = Field(ge=0, strict=True)


class Revision(Strict):
    expected_revision: int = Field(ge=0, strict=True)


class StartWorkflow(Strict):
    version_id: str = Field(min_length=1, max_length=64)
    input: str = Field(min_length=1, max_length=8000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    allow_remote_model: Literal[True]


class Review(Strict):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=1000)


class WorkflowVersion(Strict):
    id: str
    workflow_id: str
    organization_id: str
    project_id: str
    revision: int = Field(ge=1)
    graph: Graph
    digest: str


class TaskExecution(Strict):
    node_id: str
    status: Literal[
        "pending",
        "running",
        "completed",
        "waiting_review",
        "skipped",
        "failed",
        "outcome_unknown",
        "cancelled",
    ]
    core_run_id: str | None = None
    input_artifact_id: str | None = None
    output_artifact_id: str | None = None


class WorkflowRun(Strict):
    id: str
    workflow_id: str
    version_id: str
    organization_id: str
    project_id: str
    actor_id: str
    owner_id: str
    status: Literal[
        "running",
        "waiting_review",
        "completed",
        "rejected",
        "failed",
        "outcome_unknown",
        "cancelled",
    ]
    cursor: str
    input: str
    request_hash: str
    tasks: list[TaskExecution]
    artifact_id: str | None = None
    error_code: str | None = None


class Artifact(Strict):
    id: str
    organization_id: str
    project_id: str
    workflow_run_id: str
    task_id: str
    schema_name: Schema
    mime: Literal["application/json", "text/html"]
    digest: str
    length: int = Field(ge=1, le=65536)
    source_artifact_id: str | None = None
    core_run_id: str | None = None
    agent_version_id: str | None = None
    model: str | None = None
    created_at: str
    validation: Literal["text-envelope", "inert-static-document"]


class Deliverable(Strict):
    id: str
    organization_id: str
    project_id: str
    workflow_run_id: str
    artifact_id: str
    digest: str
    reviewer: str
    decision: Literal["accepted", "rejected"]
    reason: str
    created_at: str
