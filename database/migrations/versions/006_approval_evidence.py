"""Bind approved configuration to attested Bench evidence; preserve legacy records."""
import sqlalchemy as sa
from alembic import op

revision = "006_approval_evidence"
down_revision = "005_bench_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("approvals", sa.Column("evaluation_id", sa.String(64), nullable=True))
    op.add_column("approvals", sa.Column("attestation", sa.String(64), nullable=False, server_default=""))


def downgrade():
    op.drop_column("approvals", "attestation")
    op.drop_column("approvals", "evaluation_id")
