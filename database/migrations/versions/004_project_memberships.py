"""004_project_memberships
 
Revision ID: 004_project_memberships
Revises: 003_membership_status
Create Date: 2026-10-05 00:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_project_memberships'
down_revision: Union[str, None] = '003_membership_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_memberships',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('organization_id', sa.String(length=64), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='operator'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'user_id', name='uq_project_membership_user'),
    )
    op.create_index('ix_project_memberships_org_id', 'project_memberships', ['organization_id'])
    op.create_index('ix_project_memberships_project_id', 'project_memberships', ['project_id'])
    op.create_index('ix_project_memberships_user_id', 'project_memberships', ['user_id'])
    op.create_index('ix_project_membership_org_proj_user', 'project_memberships', ['organization_id', 'project_id', 'user_id'])


def downgrade() -> None:
    op.drop_index('ix_project_membership_org_proj_user', table_name='project_memberships')
    op.drop_index('ix_project_memberships_user_id', table_name='project_memberships')
    op.drop_index('ix_project_memberships_project_id', table_name='project_memberships')
    op.drop_index('ix_project_memberships_org_id', table_name='project_memberships')
    op.drop_table('project_memberships')
