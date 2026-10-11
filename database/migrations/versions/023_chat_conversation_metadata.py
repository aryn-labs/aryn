"""Add signed append-only conversation metadata and deletion tombstones."""
from alembic import op
import sqlalchemy as sa

revision = "023_chat_conversation_metadata"
down_revision = "022_chat_preferences"
branch_labels = depends_on = None


def upgrade():
    op.create_table("chat_conversation_changes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), sa.ForeignKey("chat_conversations.id"), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("attestation", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("conversation_id", "generation", name="uq_chat_metadata_generation"),
        sa.UniqueConstraint("organization_id", "project_id", "actor_id", "idempotency_key", name="uq_chat_metadata_request"))
    op.create_index("ix_chat_metadata_scope", "chat_conversation_changes", ["organization_id", "project_id", "actor_id", "conversation_id"])
    from database.chat_protection import install_chat_protection
    install_chat_protection(op.get_bind())


def downgrade():
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT COUNT(*) FROM chat_conversation_changes")).scalar():
        raise RuntimeError("Populated conversation metadata/tombstones cannot be discarded by downgrade.")
    op.drop_table("chat_conversation_changes")
