"""Scoped local evidence configuration, references and labeled interpretations."""
from alembic import op
import sqlalchemy as sa

revision = "026_evidence_connections"
down_revision = "025_bench_suite_versions"
branch_labels = depends_on = None
TABLES = ("evidence_connections", "evidence_references", "brief_interpretations")


def upgrade():
    for table in TABLES:
        columns = [sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("attestation", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        if table == "evidence_connections":
            columns.extend([sa.Column("kind", sa.String(32), nullable=False), sa.Column("revision", sa.Integer(), nullable=False)])
        elif table == "evidence_references":
            columns.append(sa.Column("connection_id", sa.String(64), sa.ForeignKey("evidence_connections.id"), nullable=False))
        else:
            columns.extend([sa.Column("bundle_id", sa.String(64), sa.ForeignKey("evidence_bundles.id"), nullable=False),
                sa.Column("core_run_id", sa.String(64), sa.ForeignKey("run_states.id"), nullable=False, unique=True)])
        op.create_table(table, *columns)
        op.create_index("ix_" + table + "_scope", table, ["organization_id", "project_id", "created_at", "id"])
    from database.intelligence_protection import install_intelligence_protection
    install_intelligence_protection(op.get_bind(), TABLES)


def downgrade():
    for table in reversed(TABLES):
        if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Signed evidence source and interpretation history cannot be discarded.")
        op.drop_table(table)
