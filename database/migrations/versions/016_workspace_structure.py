"""Scoped divisions and bounded workspace read indexes; no history backfill."""
from alembic import op
import sqlalchemy as sa

revision = "016_workspace_structure"
down_revision = "015_authentication_boundary"
branch_labels = None
depends_on = None

READ_INDEXES = (
    ("run_states", "ix_run_scope_created", ["organization_id", "project_id", "created_at", "id"]),
    ("audit_events", "ix_audit_scope_occurred", ["organization_id", "project_id", "occurred_at", "id"]),
    ("bench_evaluations", "ix_evaluation_scope_time", ["organization_id", "project_id", "evaluated_at", "id"]),
    ("agent_versions", "ix_version_blueprint_created", ["blueprint_id", "created_at", "id"]),
    ("projects", "ix_project_org_created", ["organization_id", "created_at", "id"]),
    ("agent_blueprints", "ix_blueprint_scope_created", ["organization_id", "project_id", "created_at", "id"]),
    ("agent_assignments", "ix_assignment_scope_created", ["organization_id", "project_id", "created_at", "id"]),
)


def upgrade():
    op.create_table("divisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "slug", name="uq_division_project_slug"))
    op.create_index("ix_division_scope_created", "divisions", ["organization_id", "project_id", "created_at", "id"])
    for table, name, columns in READ_INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM divisions")).scalar():
        raise RuntimeError("Export divisions before downgrade; populated workspace data cannot be dropped.")
    for table, name, _ in reversed(READ_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("divisions")
