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
    event,
    inspect,
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
    actual_model = Column(String(128), nullable=True)
    gateway = Column(String(32), nullable=True)
    runtime_backend = Column(String(32), nullable=True)
    actual_provider = Column(String(128), nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    request_hash = Column(String(64), nullable=False, default="")
    runtime_run_id = Column(String(128), nullable=True)
    execution_mode = Column(String(16), nullable=False, default="legacy")
    assignment_id = Column(String(64), nullable=True, index=True)
    agent_version_id = Column(String(64), nullable=True, index=True)
    agent_payload_hash = Column(String(64), nullable=True)
    assignment_transition_id = Column(String(64), nullable=True)
    assignment_provenance_json = Column(Text, nullable=True)
    assignment_attestation = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("ProjectModel", back_populates="runs")

    __table_args__ = (
        Index("idx_run_org_proj_status", "organization_id", "project_id", "status"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_run_project_idempotency"),
    )


@event.listens_for(RunStateModel, "before_update")
def protect_run_assignment_provenance(mapper, connection, target):
    state = inspect(target)
    protected = ("assignment_id", "agent_version_id", "agent_payload_hash", "assignment_transition_id",
        "assignment_provenance_json", "assignment_attestation")
    if any(state.attrs[key].history.has_changes() for key in protected) and not getattr(target, "_provenance_authorized", False):
        from packages.contracts.agent import VersionIntegrityError
        raise VersionIntegrityError("Run assignment provenance is immutable.")
    target._provenance_authorized = False


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
    attestation = Column(String(64), nullable=False, default="", server_default="")


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
    role = Column(String(64), nullable=True)
    objective = Column(Text, nullable=True)
    owner = Column(String(64), nullable=True)
    created_by = Column(String(64), nullable=False)
    bench_baseline_id = Column(String(64), nullable=True)
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

    schema_version = Column(String(32), default="1.0.0", nullable=False)
    role = Column(String(64), default="general_agent", nullable=False)
    objective = Column(Text, default="", nullable=False)
    owner = Column(String(64), nullable=True)
    output_contract_json = Column(Text, default="{}", nullable=False)
    constraints_json = Column(Text, default="[]", nullable=False)
    tool_policy_json = Column(Text, default="{}", nullable=False)
    model_policy_json = Column(Text, default="{}", nullable=False)
    budget_policy_json = Column(Text, default="{}", nullable=False)
    evaluation_reference_json = Column(Text, default="{}", nullable=False)

    blueprint = relationship("AgentBlueprintModel", back_populates="versions")
    assignments = relationship("AgentAssignmentModel", back_populates="version", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("blueprint_id", "version_number", name="uq_version_blueprint_number"),
    )


@event.listens_for(AgentVersionModel, "before_update")
def protect_published_configuration(mapper, connection, target):
    """Protect legitimate ORM writes, including attempts to rewrite the hash."""
    state = inspect(target)
    old_status = state.attrs.status.history.deleted
    prior = old_status[0] if old_status else target.status
    if prior in {"published", "deprecated"}:
        if target.status != prior and not (prior == "published" and target.status == "deprecated"):
            from packages.contracts.agent import VersionIntegrityError
            raise VersionIntegrityError("Published agent version status is immutable except deprecation.")
        protected = (
            "id", "blueprint_id", "version_number", "system_prompt", "model",
            "tool_grants_json", "temperature", "max_tokens", "metadata_json",
            "payload_hash", "evaluation_id", "published_at", "published_by", "created_at",
            "schema_version", "role", "objective", "owner",
            "output_contract_json", "constraints_json", "tool_policy_json",
            "model_policy_json", "budget_policy_json", "evaluation_reference_json",
        )
        if any(state.attrs[name].history.has_changes() for name in protected):
            from packages.contracts.agent import VersionIntegrityError
            raise VersionIntegrityError("Published agent version configuration is immutable.")


class AgentAssignmentModel(Base):
    __tablename__ = "agent_assignments"

    id = Column(String(64), primary_key=True)  # asgn_...
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    division_id = Column(String(64), nullable=True, index=True)
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(64), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    current_transition_id = Column(String(64), nullable=True)
    activation_origin = Column(String(16), nullable=False, default="tracked")
    role_name = Column(String(64), nullable=False)
    status = Column(String(32), default="active", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    blueprint = relationship("AgentBlueprintModel", back_populates="assignments")
    version = relationship("AgentVersionModel", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("project_id", "role_name", name="uq_assignment_project_role"),
    )


class AgentPublicationModel(Base):
    __tablename__ = "agent_publications"
    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id"), nullable=False)
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id"), nullable=False)
    version_id = Column(String(64), ForeignKey("agent_versions.id"), nullable=False, unique=True)
    details_json = Column(Text, nullable=False)
    attestation = Column(String(64), nullable=False)
    __table_args__ = (Index("ix_agent_publication_scope", "organization_id", "project_id", "blueprint_id"),)


class AssignmentTransitionModel(Base):
    __tablename__ = "assignment_transitions"
    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id"), nullable=False)
    assignment_id = Column(String(64), ForeignKey("agent_assignments.id"), nullable=False)
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id"), nullable=False)
    generation = Column(Integer, nullable=False)
    from_version_id = Column(String(64), ForeignKey("agent_versions.id"), nullable=True)
    to_version_id = Column(String(64), ForeignKey("agent_versions.id"), nullable=False)
    transition_type = Column(String(32), nullable=False)
    actor_id = Column(String(64), nullable=False)
    committed_at = Column(DateTime(timezone=True), nullable=False)
    idempotency_key = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=False)
    attestation = Column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint("assignment_id", "generation", name="uq_assignment_transition_generation"),
        UniqueConstraint("assignment_id", "idempotency_key", name="uq_assignment_transition_request"),
        Index("ix_assignment_transition_scope", "organization_id", "project_id", "assignment_id"),
    )


@event.listens_for(AgentPublicationModel, "before_update")
@event.listens_for(AgentPublicationModel, "before_delete")
@event.listens_for(AssignmentTransitionModel, "before_update")
@event.listens_for(AssignmentTransitionModel, "before_delete")
def protect_agent_governance_history(mapper, connection, target):
    from packages.contracts.agent import VersionIntegrityError
    raise VersionIntegrityError("Agent publication and activation evidence is append-only.")


@event.listens_for(AgentAssignmentModel, "before_update")
def protect_assignment_activation(mapper, connection, target):
    state = inspect(target)
    if any(state.attrs[key].history.has_changes() for key in (
        "id", "organization_id", "project_id", "blueprint_id", "division_id", "role_name", "created_at",
        "version_id", "current_transition_id", "activation_origin",
    )) and not getattr(target, "_activation_authorized", False):
        from packages.contracts.agent import VersionIntegrityError
        raise VersionIntegrityError("Assignment activation requires governed transition authority.")
    target._activation_authorized = False


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
    evaluation_id = Column(String(64), nullable=True)
    attestation = Column(String(64), nullable=False, default="")
    regression_comparison_id = Column(String(64), nullable=True)


class BenchBaselineModel(Base):
    __tablename__ = "bench_baselines"
    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id"), nullable=False)
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id"), nullable=False)
    generation = Column(Integer, nullable=False)
    evaluation_id = Column(String(64), ForeignKey("bench_evaluations.id"), nullable=False)
    version_id = Column(String(64), ForeignKey("agent_versions.id"), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    suite_id = Column(String(128), nullable=False)
    evaluation_version = Column(String(32), nullable=False)
    suite_hash = Column(String(64), nullable=False)
    accepted_by = Column(String(64), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=False)
    supersedes_id = Column(String(64), ForeignKey("bench_baselines.id"), nullable=True)
    details_json = Column(Text, nullable=False)
    attestation = Column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "blueprint_id", "generation", name="uq_bench_baseline_generation"),
        Index("ix_bench_baseline_scope", "organization_id", "project_id", "blueprint_id"),
    )


class BenchComparisonModel(Base):
    __tablename__ = "bench_comparisons"
    id = Column(String(64), primary_key=True)
    organization_id = Column(String(64), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(String(64), ForeignKey("projects.id"), nullable=False)
    blueprint_id = Column(String(64), ForeignKey("agent_blueprints.id"), nullable=False)
    baseline_id = Column(String(64), ForeignKey("bench_baselines.id"), nullable=True)
    candidate_evaluation_id = Column(String(64), ForeignKey("bench_evaluations.id"), nullable=False)
    compared_at = Column(DateTime(timezone=True), nullable=False)
    details_json = Column(Text, nullable=False)
    attestation = Column(String(64), nullable=False)
    __table_args__ = (Index("ix_bench_comparison_scope", "organization_id", "project_id", "blueprint_id", "candidate_evaluation_id"),)


@event.listens_for(BenchBaselineModel, "before_update")
@event.listens_for(BenchBaselineModel, "before_delete")
@event.listens_for(BenchComparisonModel, "before_update")
@event.listens_for(BenchComparisonModel, "before_delete")
def protect_bench_governance_history(mapper, connection, target):
    raise ValueError("Bench governance evidence is append-only.")


@event.listens_for(Base.metadata, "after_create")
def install_governance_guards(metadata, connection, **kwargs):
    from database.governance_protection import install_history_protection
    install_history_protection(connection)
