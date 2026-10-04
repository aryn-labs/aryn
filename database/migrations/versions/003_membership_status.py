"""003_membership_status

Revision ID: 003_membership_status
Revises: 002_agent_factory_and_bench
Create Date: 2026-10-04 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_membership_status'
down_revision: Union[str, None] = '002_agent_factory_and_bench'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('memberships', sa.Column('status', sa.String(length=32), nullable=False, server_default='active'))


def downgrade() -> None:
    op.drop_column('memberships', 'status')
