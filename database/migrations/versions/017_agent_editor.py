"""Mutable scoped drafts and private layout metadata; immutable versions untouched."""
from alembic import op
import sqlalchemy as sa

revision = "017_agent_editor"
down_revision = "016_workspace_structure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_working_copies",
        sa.Column("blueprint_id", sa.String(64), sa.ForeignKey("agent_blueprints.id"), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=True),
        sa.Column("source_version_id", sa.String(64), sa.ForeignKey("agent_versions.id"), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_working_copy_scope", "agent_working_copies", ["organization_id", "project_id", "blueprint_id"])
    op.create_table("agent_editor_layouts",
        sa.Column("blueprint_id", sa.String(64), sa.ForeignKey("agent_blueprints.id"), primary_key=True),
        sa.Column("actor_id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("layout_json", sa.Text(), nullable=False))
    op.create_index("ix_editor_layout_scope", "agent_editor_layouts", ["organization_id", "project_id", "blueprint_id"])


def downgrade():
    for table in ("agent_working_copies", "agent_editor_layouts"):
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Export editor records before downgrade; stored drafts/layout cannot be dropped.")
    op.drop_table("agent_editor_layouts")
    op.drop_table("agent_working_copies")
