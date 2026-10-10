"""Add personal locale preferences and signed, revocable provider consent."""
from alembic import op
import sqlalchemy as sa

revision = "022_chat_preferences"
down_revision = "021_chat_conversations"
branch_labels = depends_on = None


def upgrade():
    op.create_table("chat_provider_consents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("policy", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.String(40), nullable=False),
        sa.Column("revoked_at", sa.String(40), nullable=True),
        sa.Column("attestation", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "project_id", "actor_id", "provider_id", name="uq_chat_provider_consent"))
    op.create_table("studio_preferences",
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("actor_id", sa.String(64), primary_key=True),
        sa.Column("locale", sa.String(8), nullable=False))


def downgrade():
    if not op.get_context().as_sql:
        for table in ("chat_provider_consents", "studio_preferences"):
            if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
                raise RuntimeError("Populated personal settings cannot be discarded by downgrade.")
    op.drop_table("studio_preferences")
    op.drop_table("chat_provider_consents")
