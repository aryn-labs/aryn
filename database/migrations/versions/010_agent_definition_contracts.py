"""010_agent_definition_contracts

Revision ID: 010_agent_definition_contracts
Revises: 009_gateway_provenance
Create Date: 2026-10-07 10:36:00.000000

Adds explicit first-class Agent Definition fields to agent_blueprints and agent_versions:
- role, objective, owner on agent_blueprints
- schema_version, role, objective, owner, output_contract_json, constraints_json,
  tool_policy_json, model_policy_json, budget_policy_json, evaluation_reference_json
  on agent_versions
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010_agent_definition_contracts"
down_revision: Union[str, None] = "009_gateway_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_blueprints columns
    op.add_column("agent_blueprints", sa.Column("role", sa.String(length=64), nullable=True))
    op.add_column("agent_blueprints", sa.Column("objective", sa.Text(), nullable=True))
    op.add_column("agent_blueprints", sa.Column("owner", sa.String(length=64), nullable=True))

    # 2. agent_versions columns
    op.add_column(
        "agent_versions",
        sa.Column("schema_version", sa.String(length=32), nullable=False, server_default="1.0.0"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("role", sa.String(length=64), nullable=False, server_default="general_agent"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("objective", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_versions",
        sa.Column("owner", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_versions",
        sa.Column("output_contract_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("constraints_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("tool_policy_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("model_policy_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("budget_policy_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agent_versions",
        sa.Column("evaluation_reference_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    for col in (
        "evaluation_reference_json",
        "budget_policy_json",
        "model_policy_json",
        "tool_policy_json",
        "constraints_json",
        "output_contract_json",
        "owner",
        "objective",
        "role",
        "schema_version",
    ):
        op.drop_column("agent_versions", col)

    for col in ("owner", "objective", "role"):
        op.drop_column("agent_blueprints", col)
