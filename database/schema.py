"""SQLAlchemy schema models for ARYN infrastructure.

Defines models for Organization, Project, Membership, RunState, AuditEvent, UsageBudget,
AgentBlueprint, AgentVersion, AgentAssignment, BenchEvaluation, and Approval.
Compliant with SQLite for local development and PostgreSQL Cloud.
Complies with ARYN-ARCH-001 Section 04 and ARYN-SEC-001.
"""

from __future__ import annotations

import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class OrganizationModel(Base):
    __tablename__ = "organizations"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    projects = relationship("ProjectModel", back_populates="organization", cascade="all, delete-orphan")
    memberships = relationship("MembershipModel", back_populates="organization", cascade="all, delete-orphan")


class ProjectModel(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organization = relationship("OrganizationModel", back_populates="projects")
    runs = relationship("RunStateModel", back_populates="project", cascade="all, delete-orphan")
    blueprints = relationship("AgentBlueprintModel", back_populates="project", cascade="all, delete-orphan")
    project_memberships = relationship("ProjectMembershipModel", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),
    )


class MembershipModel(Base):
    __tablename__ = "memberships"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="operator")  # admin, operator, viewer
    status = Column(String(32), nullable=False, default="active")  # active, revoked, suspended
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organization = relationship("OrganizationModel", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )


class ProjectMembershipModel(Base):
    __tablename__ = "project_memberships"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="operator")  # operator, viewer
    status = Column(String(32), nullable=False, default="active")  # active, revoked, suspended
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organization = relationship("OrganizationModel")
    project = relationship("ProjectModel", back_populates="project_memberships")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_membership_user"),
        Index("ix_project_membership_org_proj_user", "organization_id", "project_id", "user_id"),
    )


class RunStateModel(Base):
    __tablename__ = "run_states"

    id = Column(String(64), primary_key=True)  # run_...
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    prompt = Column(Text, nullable=False)
    output = Column(Text, nullable=True)
    model = Column(String(128), nullable=False)
    provider = Column(String(64), nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("ProjectModel", back_populates="runs")

    __table_args__ = (
        Index("idx_run_org_proj_status", "organization_id", "project_id", "status"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_run_project_idempotency"),
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True)  # evt_...
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    event_type = Column(String(128), nullable=False, index=True)
    schema_version = Column(String(16), nullable=False, default="1.0.0")
    occurred_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    organization_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    actor_type = Column(String(32), nullable=False)
    actor_id = Column(String(64), nullable=False, index=True)
    correlation_id = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(128), nullable=False, index=True)
    causation_id = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False)
    redacted_payload_json = Column(Text, nullable=False)
    integrity_reference = Column(String(64), nullable=False)  # SHA-256


class UsageBudgetModel(Base):
    __tablename__ = "usage_budgets"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    max_tokens_per_run = Column(Integer, default=4096, nullable=False)
    max_turns = Column(Integer, default=10, nullable=False)
    max_cost_usd = Column(Float, default=0.50, nullable=False)
    cumulative_tokens = Column(Integer, default=0, nullable=False)
    cumulative_cost_usd = Column(Float, default=0.0, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", name="uq_usage_org_proj"),
    )


class AgentBlueprintModel(Base):
    __tablename__ = "agent_blueprints"

    id = Column(String(64), primary_key=True)  # abp_...
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("ProjectModel", back_populates="blueprints")
    versions = relationship("AgentVersionModel", back_populates="blueprint", cascade="all, delete-orphan")
    assignments = relationship("AgentAssignmentModel", back_populates="blueprint", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_blueprint_project_slug"),
    )


class AgentVersionModel(Base):
    __tablename__ = "agent_versions"

    id = Column(String(64), primary_key=True)  # av_...
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(String(32), nullable=False)
    status = Column(String(32), default="draft", nullable=False, index=True)  # draft, evaluating, approved, published, deprecated, rejected
    system_prompt = Column(Text, nullable=False)
    model = Column(String(128), nullable=False)
    tool_grants_json = Column(Text, nullable=False, default="[]")
    temperature = Column(Float, default=0.7, nullable=False)
    max_tokens = Column(Integer, default=2048, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    payload_hash = Column(String(64), nullable=False, index=True)
    evaluation_id = Column(String(64), nullable=True, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    blueprint = relationship("AgentBlueprintModel", back_populates="versions")
    assignments = relationship("AgentAssignmentModel", back_populates="version", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("blueprint_id", "version_number", name="uq_version_blueprint_number"),
    )


class AgentAssignmentModel(Base):
    __tablename__ = "agent_assignments"

    id = Column(String(64), primary_key=True)  # asgn_...
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    division_id = Column(String(64), nullable=True, index=True)
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(64), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    role_name = Column(String(64), nullable=False)
    status = Column(String(32), default="active", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    blueprint = relationship("AgentBlueprintModel", back_populates="assignments")
    version = relationship("AgentVersionModel", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("project_id", "role_name", name="uq_assignment_project_role"),
    )


class BenchEvaluationModel(Base):
    __tablename__ = "bench_evaluations"

    id = Column(String(64), primary_key=True)  # eval_...
    organization_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    blueprint_id = Column(String(64), nullable=False, index=True)
    version_id = Column(String(64), nullable=False, index=True)
    passed = Column(Integer, nullable=False)  # 1 or 0
    total_scenarios = Column(Integer, nullable=False)
    passed_scenarios = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)
    details_json = Column(Text, nullable=False)
    evaluated_by = Column(String(64), nullable=False)
    evaluated_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    provenance_json = Column(Text, nullable=False, default="{}")


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id = Column(String(64), primary_key=True)  # appr_...
    organization_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=False, index=True)
    target_type = Column(String(32), nullable=False)
    target_id = Column(String(64), nullable=False, index=True)
    payload_hash = Column(String(64), nullable=False, index=True)
    approved_by = Column(String(64), nullable=False)
    status = Column(String(32), default="approved", nullable=False)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
