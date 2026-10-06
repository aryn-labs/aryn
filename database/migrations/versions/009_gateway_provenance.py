"""Preserve legacy runs without inventing gateway/provider provenance."""
import sqlalchemy as sa
from alembic import op

revision = "009_gateway_provenance"
down_revision = "008_unique_run_claim"
branch_labels = None
depends_on = None


def upgrade():
    for name, length in (("actual_model", 128), ("gateway", 32), ("runtime_backend", 32), ("actual_provider", 128)):
        op.add_column("run_states", sa.Column(name, sa.String(length), nullable=True))


def downgrade():
    for name in ("actual_provider", "runtime_backend", "gateway", "actual_model"):
        op.drop_column("run_states", name)
