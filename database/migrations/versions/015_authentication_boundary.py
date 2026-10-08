"""Provisioned external identities and expiring server sessions. No seeded authority."""
from alembic import op
import sqlalchemy as sa

revision = "015_authentication_boundary"
down_revision = "014_execution_authority"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("external_identities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_external_identity_subject"))
    op.create_table("auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("identity_id", sa.String(64), sa.ForeignKey("external_identities.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_table("login_transactions",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("login_transactions")
    op.drop_table("auth_sessions")
    op.drop_table("external_identities")
