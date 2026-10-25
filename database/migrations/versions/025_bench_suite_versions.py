"""Immutable scoped suite versions and reviewed regression candidates."""
from alembic import op
import sqlalchemy as sa

revision = "025_bench_suite_versions"
down_revision = "024_project_metadata"
branch_labels = depends_on = None
TABLES = ("bench_suite_versions", "bench_scenario_candidates")


def upgrade():
    for table in TABLES:
        columns = [sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("attestation", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        if table == "bench_suite_versions":
            columns.extend([sa.Column("family_key", sa.String(64), nullable=False),
                sa.Column("evaluation_version", sa.String(32), nullable=False),
                sa.UniqueConstraint("organization_id", "project_id", "family_key", "evaluation_version",
                    name="uq_bench_suite_version")])
        else:
            columns.extend([sa.Column("source_kind", sa.String(32), nullable=False),
                sa.Column("source_id", sa.String(64), nullable=False)])
        op.create_table(table, *columns)
        op.create_index("ix_" + table + "_scope", table, ["organization_id", "project_id", "created_at", "id"])
    from database.intelligence_protection import install_intelligence_protection
    install_intelligence_protection(op.get_bind(), TABLES)


def downgrade():
    for table in reversed(TABLES):
        if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Signed suite and candidate history cannot be discarded.")
        op.drop_table(table)
