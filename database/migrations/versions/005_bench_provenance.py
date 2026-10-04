"""Persist Bench suite, requested model, and configuration hash provenance."""
import sqlalchemy as sa
from alembic import op

revision = "005_bench_provenance"
down_revision = "004_project_memberships"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("bench_evaluations", sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"))

def downgrade():
    op.drop_column("bench_evaluations", "provenance_json")
