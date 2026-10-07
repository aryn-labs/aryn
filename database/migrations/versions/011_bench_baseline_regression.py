"""Durable accepted Bench baselines and regression governance evidence."""
from alembic import op
import sqlalchemy as sa

revision = "011_bench_baseline_regression"
down_revision = "010_agent_definition_contracts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_blueprints", sa.Column("bench_baseline_id", sa.String(64), nullable=True))
    op.add_column("approvals", sa.Column("regression_comparison_id", sa.String(64), nullable=True))
    op.create_table("bench_baselines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("blueprint_id", sa.String(64), sa.ForeignKey("agent_blueprints.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.String(64), sa.ForeignKey("bench_evaluations.id"), nullable=False),
        sa.Column("version_id", sa.String(64), sa.ForeignKey("agent_versions.id"), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("suite_id", sa.String(128), nullable=False),
        sa.Column("evaluation_version", sa.String(32), nullable=False),
        sa.Column("suite_hash", sa.String(64), nullable=False),
        sa.Column("accepted_by", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_id", sa.String(64), sa.ForeignKey("bench_baselines.id"), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("attestation", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "project_id", "blueprint_id", "generation", name="uq_bench_baseline_generation"))
    op.create_index("ix_bench_baseline_scope", "bench_baselines", ["organization_id", "project_id", "blueprint_id"])
    op.create_table("bench_comparisons",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("blueprint_id", sa.String(64), sa.ForeignKey("agent_blueprints.id"), nullable=False),
        sa.Column("baseline_id", sa.String(64), sa.ForeignKey("bench_baselines.id"), nullable=True),
        sa.Column("candidate_evaluation_id", sa.String(64), sa.ForeignKey("bench_evaluations.id"), nullable=False),
        sa.Column("compared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("attestation", sa.String(64), nullable=False))
    op.create_index("ix_bench_comparison_scope", "bench_comparisons", ["organization_id", "project_id", "blueprint_id", "candidate_evaluation_id"])


def downgrade():
    op.drop_table("bench_comparisons")
    op.drop_table("bench_baselines")
    op.drop_column("approvals", "regression_comparison_id")
    op.drop_column("agent_blueprints", "bench_baseline_id")
