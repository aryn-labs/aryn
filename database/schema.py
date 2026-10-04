"""SQLAlchemy schema models for ARYN infrastructure.

Defines models for Organization, Project, Membership, RunState, AuditEvent, and UsageBudget.
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

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),
    )


class MembershipModel(Base):
    __tablename__ = "memberships"

    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="operator")  # admin, operator, viewer
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organization = relationship("OrganizationModel", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
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
        Index("idx_run_proj_idempotency", "project_id", "idempotency_key"),
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
