"""Add editable project objectives and durable idempotency receipts."""
from alembic import op
import sqlalchemy as sa

revision = "024_project_metadata"
down_revision = "023_chat_conversation_metadata"
branch_labels = depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("projects", sa.Column("generation", sa.Integer(), nullable=False, server_default="1"))
    op.create_table("project_mutations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("attestation", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "actor_id", "idempotency_key", name="uq_project_mutation_request"))
    from database.project_protection import install_project_protection
    install_project_protection(op.get_bind())


def downgrade():
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT COUNT(*) FROM project_mutations")).scalar():
        raise RuntimeError("Project mutation history cannot be discarded.")
    op.drop_table("project_mutations")
    op.drop_column("projects", "generation")
    op.drop_column("projects", "description")
