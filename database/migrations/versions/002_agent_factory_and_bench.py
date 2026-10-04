"""002_agent_factory_and_bench

Revision ID: 002_agent_factory_and_bench
Revises: 001_initial_core
Create Date: 2026-10-04 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_agent_factory_and_bench'
down_revision: Union[str, None] = '001_initial_core'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_blueprints
    op.create_table(
        'agent_blueprints',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('project_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'slug', name='uq_blueprint_project_slug')
    )
    op.create_index(op.f('ix_agent_blueprints_organization_id'), 'agent_blueprints', ['organization_id'], unique=False)
    op.create_index(op.f('ix_agent_blueprints_project_id'), 'agent_blueprints', ['project_id'], unique=False)

    # 2. agent_versions
    op.create_table(
        'agent_versions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('blueprint_id', sa.String(length=64), nullable=False),
        sa.Column('version_number', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('tool_grants_json', sa.Text(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('max_tokens', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('evaluation_id', sa.String(length=64), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['blueprint_id'], ['agent_blueprints.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('blueprint_id', 'version_number', name='uq_version_blueprint_number')
    )
    op.create_index(op.f('ix_agent_versions_blueprint_id'), 'agent_versions', ['blueprint_id'], unique=False)
    op.create_index(op.f('ix_agent_versions_evaluation_id'), 'agent_versions', ['evaluation_id'], unique=False)
    op.create_index(op.f('ix_agent_versions_payload_hash'), 'agent_versions', ['payload_hash'], unique=False)
    op.create_index(op.f('ix_agent_versions_status'), 'agent_versions', ['status'], unique=False)

    # 3. agent_assignments
    op.create_table(
        'agent_assignments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('project_id', sa.String(length=64), nullable=False),
        sa.Column('division_id', sa.String(length=64), nullable=True),
        sa.Column('blueprint_id', sa.String(length=64), nullable=False),
        sa.Column('version_id', sa.String(length=64), nullable=False),
        sa.Column('role_name', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blueprint_id'], ['agent_blueprints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['version_id'], ['agent_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'role_name', name='uq_assignment_project_role')
    )
    op.create_index(op.f('ix_agent_assignments_blueprint_id'), 'agent_assignments', ['blueprint_id'], unique=False)
    op.create_index(op.f('ix_agent_assignments_division_id'), 'agent_assignments', ['division_id'], unique=False)
    op.create_index(op.f('ix_agent_assignments_organization_id'), 'agent_assignments', ['organization_id'], unique=False)
    op.create_index(op.f('ix_agent_assignments_project_id'), 'agent_assignments', ['project_id'], unique=False)
    op.create_index(op.f('ix_agent_assignments_status'), 'agent_assignments', ['status'], unique=False)
    op.create_index(op.f('ix_agent_assignments_version_id'), 'agent_assignments', ['version_id'], unique=False)

    # 4. bench_evaluations
    op.create_table(
        'bench_evaluations',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('project_id', sa.String(length=64), nullable=False),
        sa.Column('blueprint_id', sa.String(length=64), nullable=False),
        sa.Column('version_id', sa.String(length=64), nullable=False),
        sa.Column('passed', sa.Integer(), nullable=False),
        sa.Column('total_scenarios', sa.Integer(), nullable=False),
        sa.Column('passed_scenarios', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('details_json', sa.Text(), nullable=False),
        sa.Column('evaluated_by', sa.String(length=64), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bench_evaluations_blueprint_id'), 'bench_evaluations', ['blueprint_id'], unique=False)
    op.create_index(op.f('ix_bench_evaluations_organization_id'), 'bench_evaluations', ['organization_id'], unique=False)
    op.create_index(op.f('ix_bench_evaluations_project_id'), 'bench_evaluations', ['project_id'], unique=False)
    op.create_index(op.f('ix_bench_evaluations_version_id'), 'bench_evaluations', ['version_id'], unique=False)

    # 5. approvals
    op.create_table(
        'approvals',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('project_id', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=64), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('approved_by', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approvals_organization_id'), 'approvals', ['organization_id'], unique=False)
    op.create_index(op.f('ix_approvals_payload_hash'), 'approvals', ['payload_hash'], unique=False)
    op.create_index(op.f('ix_approvals_project_id'), 'approvals', ['project_id'], unique=False)
    op.create_index(op.f('ix_approvals_target_id'), 'approvals', ['target_id'], unique=False)


def downgrade() -> None:
    op.drop_table('approvals')
    op.drop_table('bench_evaluations')
    op.drop_table('agent_assignments')
    op.drop_table('agent_versions')
    op.drop_table('agent_blueprints')
