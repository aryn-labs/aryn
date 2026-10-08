"""Authenticated audit and append-only governance persistence; no evidence backfill."""
from alembic import op
import sqlalchemy as sa

from database.governance_protection import install_history_protection, remove_history_protection

revision = "013_history_integrity"
down_revision = "012_assignment_activation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_events", sa.Column("attestation", sa.String(64), nullable=False, server_default=""))
    install_history_protection(op.get_bind())


def downgrade():
    remove_history_protection(op.get_bind())
    op.drop_column("audit_events", "attestation")
