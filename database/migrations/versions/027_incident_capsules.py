"""Operational incident snapshots and diagnostic replays; retain historical evidence."""
from alembic import op
import sqlalchemy as sa

revision = "027_incident_capsules"
down_revision = "026_evidence_connections"
branch_labels = depends_on = None
TABLES = ("incident_capsules", "incident_capsule_replays")


def upgrade():
    for table in TABLES:
        columns = [sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("attestation", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        if table == "incident_capsules":
            columns.extend([sa.Column("incident_id", sa.String(64), sa.ForeignKey("relay_incidents.id"), nullable=False),
                sa.Column("incident_revision", sa.Integer(), nullable=False),
                sa.UniqueConstraint("incident_id", "incident_revision", name="uq_incident_capsule_revision")])
        else:
            columns.append(sa.Column("capsule_id", sa.String(64), sa.ForeignKey("incident_capsules.id"), nullable=False))
        op.create_table(table, *columns)
        op.create_index("ix_" + table + "_scope", table, ["organization_id", "project_id", "created_at", "id"])
    from database.intelligence_protection import install_intelligence_protection
    install_intelligence_protection(op.get_bind(), TABLES)


def downgrade():
    for table in reversed(TABLES):
        if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Signed incident capsules and replay history cannot be discarded.")
        op.drop_table(table)
