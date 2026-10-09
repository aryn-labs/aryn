"""Empty Core schedules/checkpoints, preserving all governed history through 019."""

from alembic import op
import sqlalchemy as sa
from database.automation_protection import install_automation_protection

revision = "020_core_automations"
down_revision = "019_intelligence_recovery"
branch_labels = depends_on = None
TABLES = ("automation_definitions", "automation_occurrences", "automation_events")


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
        if table == "automation_definitions":
            columns.extend(
                [
                    sa.Column("title", sa.String(160), nullable=False),
                    sa.Column("revision", sa.Integer(), nullable=False),
                    sa.Column("status", sa.String(32), nullable=False),
                    sa.Column("next_run_at", sa.String(40), nullable=False),
                ]
            )
        else:
            columns.append(
                sa.Column(
                    "automation_id",
                    sa.String(64),
                    sa.ForeignKey("automation_definitions.id"),
                    nullable=False,
                )
            )
        if table == "automation_occurrences":
            columns.extend(
                [
                    sa.Column("occurrence_key", sa.String(160), nullable=False),
                    sa.Column("status", sa.String(32), nullable=False),
                    sa.Column("admitted_at", sa.String(40), nullable=True),
                    sa.UniqueConstraint(
                        "automation_id",
                        "occurrence_key",
                        name="uq_automation_occurrence",
                    ),
                ]
            )
        op.create_table(table, *columns)
        op.create_index(
            "ix_" + table + "_scope",
            table,
            ["organization_id", "project_id", "created_at", "id"],
        )
    op.create_index(
        "ix_automation_due", "automation_definitions", ["status", "next_run_at"]
    )
    op.create_index(
        "ix_automation_occurrence_status",
        "automation_occurrences",
        ["automation_id", "status"],
    )
    op.create_index(
        "ix_automation_occurrence_admitted",
        "automation_occurrences",
        ["automation_id", "admitted_at"],
    )
    op.create_index(
        "ix_automation_event_definition",
        "automation_events",
        ["automation_id", "created_at"],
    )
    install_automation_protection(op.get_bind())


def downgrade():
    connection = op.get_bind()
    if not op.get_context().as_sql:
        if any(
            connection.execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar()
            for table in TABLES
        ):
            raise RuntimeError("Populated Core schedules/history cannot be downgraded.")
    for table in reversed(TABLES):
        op.drop_table(table)
