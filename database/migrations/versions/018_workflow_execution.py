"""Additive scoped workflow records; no existing evidence backfill."""

from alembic import op
import sqlalchemy as sa

revision = "018_workflow_execution"
down_revision = "017_agent_editor"
branch_labels = None
depends_on = None

TABLES = (
    "workflow_definitions",
    "workflow_versions",
    "workflow_runs",
    "workflow_artifacts",
    "workflow_deliverables",
)


def upgrade():
    for table in TABLES:
        columns = [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(64),
                sa.ForeignKey("organizations.id"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(64),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("attestation", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ]
        if table in ("workflow_definitions", "workflow_versions"):
            columns.append(sa.Column("revision", sa.Integer(), nullable=False))
        if table in ("workflow_versions", "workflow_runs"):
            columns.append(
                sa.Column(
                    "workflow_id",
                    sa.String(64),
                    sa.ForeignKey("workflow_definitions.id"),
                    nullable=False,
                )
            )
        if table == "workflow_versions":
            columns.append(
                sa.UniqueConstraint(
                    "workflow_id", "revision", name="uq_workflow_version_revision"
                )
            )
        if table == "workflow_runs":
            columns.append(sa.Column("status", sa.String(32), nullable=False))
            columns.extend(
                [
                    sa.Column(
                        "version_id",
                        sa.String(64),
                        sa.ForeignKey("workflow_versions.id"),
                        nullable=False,
                    ),
                    sa.Column("idempotency_key", sa.String(128), nullable=False),
                    sa.UniqueConstraint(
                        "organization_id",
                        "project_id",
                        "idempotency_key",
                        name="uq_workflow_start",
                    ),
                ]
            )
        if table in ("workflow_artifacts", "workflow_deliverables"):
            columns.append(
                sa.Column(
                    "workflow_run_id",
                    sa.String(64),
                    sa.ForeignKey("workflow_runs.id"),
                    nullable=False,
                    unique=table == "workflow_deliverables",
                )
            )
        if table == "workflow_artifacts":
            columns.append(sa.Column("blob", sa.LargeBinary(), nullable=False))
        if table == "workflow_deliverables":
            columns.append(
                sa.Column(
                    "artifact_id",
                    sa.String(64),
                    sa.ForeignKey("workflow_artifacts.id"),
                    nullable=False,
                )
            )
        op.create_table(table, *columns)
    op.create_index(
        "ix_workflow_definition_scope",
        "workflow_definitions",
        ["organization_id", "project_id", "id"],
    )
    op.create_index(
        "ix_workflow_run_scope",
        "workflow_runs",
        ["organization_id", "project_id", "workflow_id"],
    )
    op.create_index(
        "ix_workflow_artifact_scope",
        "workflow_artifacts",
        ["organization_id", "project_id", "workflow_run_id"],
    )
    from database.workflow_protection import install_workflow_protection

    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    install_workflow_protection(op.get_bind())


def downgrade():
    counts = [
        op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        for table in TABLES
    ]
    if any(counts):
        raise RuntimeError(
            "Export workflow evidence before downgrade; populated history cannot be dropped."
        )
    for table in reversed(TABLES):
        op.drop_table(table)
