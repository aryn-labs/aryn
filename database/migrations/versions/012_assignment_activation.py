"""Immutable publication receipts, assignment activation history and run provenance."""
from alembic import op
import sqlalchemy as sa

revision = "012_assignment_activation"
down_revision = "011_bench_baseline_regression"
branch_labels = None
depends_on = None


def scope_columns():
    return [sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("blueprint_id", sa.String(64), sa.ForeignKey("agent_blueprints.id"), nullable=False)]


def upgrade():
    op.add_column("agent_assignments", sa.Column("current_transition_id", sa.String(64), nullable=True))
    op.add_column("agent_assignments", sa.Column("activation_origin", sa.String(16), nullable=False, server_default="legacy"))
    for name in ("assignment_id", "agent_version_id", "agent_payload_hash", "assignment_transition_id", "assignment_attestation"):
        op.add_column("run_states", sa.Column(name, sa.String(64), nullable=True))
    op.add_column("run_states", sa.Column("assignment_provenance_json", sa.Text(), nullable=True))
    for name in ("assignment_id", "agent_version_id"):
        op.create_index("ix_run_states_" + name, "run_states", [name])
    op.create_table("agent_publications", *scope_columns(),
        sa.Column("version_id", sa.String(64), sa.ForeignKey("agent_versions.id"), nullable=False, unique=True),
        sa.Column("details_json", sa.Text(), nullable=False), sa.Column("attestation", sa.String(64), nullable=False))
    op.create_index("ix_agent_publication_scope", "agent_publications", ["organization_id", "project_id", "blueprint_id"])
    op.create_table("assignment_transitions", *scope_columns(),
        sa.Column("assignment_id", sa.String(64), sa.ForeignKey("agent_assignments.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("from_version_id", sa.String(64), sa.ForeignKey("agent_versions.id"), nullable=True),
        sa.Column("to_version_id", sa.String(64), sa.ForeignKey("agent_versions.id"), nullable=False),
        sa.Column("transition_type", sa.String(32), nullable=False), sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False), sa.Column("attestation", sa.String(64), nullable=False),
        sa.UniqueConstraint("assignment_id", "generation", name="uq_assignment_transition_generation"),
        sa.UniqueConstraint("assignment_id", "idempotency_key", name="uq_assignment_transition_request"))
    op.create_index("ix_assignment_transition_scope", "assignment_transitions", ["organization_id", "project_id", "assignment_id"])


def downgrade():
    op.drop_table("assignment_transitions")
    op.drop_table("agent_publications")
    op.drop_column("agent_assignments", "current_transition_id")
    op.drop_column("agent_assignments", "activation_origin")
    for name in ("assignment_id", "agent_version_id"):
        op.drop_index("ix_run_states_" + name, table_name="run_states")
    for name in ("assignment_id", "agent_version_id", "agent_payload_hash", "assignment_transition_id", "assignment_attestation", "assignment_provenance_json"):
        op.drop_column("run_states", name)
