"""Persist execution fingerprints and distinct Core/runtime identifiers."""
import sqlalchemy as sa
from alembic import op

revision = "007_execution_claim"
down_revision = "006_approval_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("run_states", sa.Column("request_hash", sa.String(64), nullable=False, server_default=""))
    op.add_column("run_states", sa.Column("runtime_run_id", sa.String(128), nullable=True))
    op.add_column("run_states", sa.Column("execution_mode", sa.String(16), nullable=False, server_default="legacy"))


def downgrade():
    op.drop_column("run_states", "execution_mode")
    op.drop_column("run_states", "runtime_run_id")
    op.drop_column("run_states", "request_hash")
