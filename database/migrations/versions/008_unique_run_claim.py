"""Enforce the execution claim on migrated databases, preserving all legacy runs."""
import sqlalchemy as sa
from alembic import context, op

revision = "008_unique_run_claim"
down_revision = "007_execution_claim"
branch_labels = None
depends_on = None


def upgrade():
    if not context.is_offline_mode():
        duplicates = op.get_bind().execute(sa.text(
            "SELECT project_id FROM run_states WHERE idempotency_key IS NOT NULL "
            "GROUP BY project_id, idempotency_key HAVING COUNT(*) > 1"
        )).first()
        if duplicates:
            raise RuntimeError(
                "Database memiliki key eksekusi duplikat. Tinjau duplikasi sebelum migrasi; riwayat tidak dihapus otomatis."
            )
    op.create_index("uq_run_project_claim", "run_states", ["project_id", "idempotency_key"], unique=True)


def downgrade():
    op.drop_index("uq_run_project_claim", table_name="run_states")
