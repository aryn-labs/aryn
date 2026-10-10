"""Add scoped conversations without rewriting existing Core execution history."""
from alembic import op
import sqlalchemy as sa

revision = "021_chat_conversations"
down_revision = "020_core_automations"
branch_labels = depends_on = None


def upgrade():
    op.create_table("chat_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_chat_conversation_scope", "chat_conversations", ["organization_id", "project_id", "actor_id", "updated_at"])
    op.create_table("chat_turns",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), sa.ForeignKey("chat_conversations.id"), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("run_states.id"), nullable=False),
        sa.Column("attestation", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "project_id", "actor_id", "idempotency_key", name="uq_chat_turn_request"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_chat_turn_sequence"))


def downgrade():
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT COUNT(*) FROM chat_conversations")).scalar():
        raise RuntimeError("Populated conversation history cannot be discarded by downgrade.")
    op.drop_table("chat_turns")
    op.drop_table("chat_conversations")
