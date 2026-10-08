"""Core execution ownership, reservation and evidence availability.

Revision ID: 014_execution_authority
Revises: 013_history_integrity
"""
from alembic import op
import sqlalchemy as sa

revision = "014_execution_authority"
down_revision = "013_history_integrity"
branch_labels = None
depends_on = None

RUN_COLUMNS = [
    sa.Column("execution_claim_json", sa.Text()),
    sa.Column("execution_attestation", sa.String(64)),
    sa.Column("execution_owner_id", sa.String(64)),
    sa.Column("deadline_at", sa.DateTime(timezone=True)),
    sa.Column("effective_limits_json", sa.Text(), nullable=False, server_default="{}"),
    sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("usage_settled", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("usage_availability", sa.String(32), nullable=False, server_default="unavailable"),
    sa.Column("usage_cost_usd", sa.Float()),
    sa.Column("usage_cost_source", sa.String(64)),
    sa.Column("error_code", sa.String(64)),
]

def upgrade():
    for column in RUN_COLUMNS:
        op.add_column("run_states", column)
    op.add_column("usage_budgets", sa.Column("max_total_tokens", sa.Integer()))
    op.add_column("usage_budgets", sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agent_versions", sa.Column("evaluation_owner_id", sa.String(64)))

def downgrade():
    op.drop_column("agent_versions", "evaluation_owner_id")
    op.drop_column("usage_budgets", "reserved_tokens")
    op.drop_column("usage_budgets", "max_total_tokens")
    for column in reversed(RUN_COLUMNS):
        op.drop_column("run_states", column.name)
