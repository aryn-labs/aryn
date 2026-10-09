"""Scoped Brief evidence and disposable Relay recovery; no historical backfill."""

from alembic import op
import sqlalchemy as sa
from database.intelligence_protection import install_intelligence_protection

revision = "019_intelligence_recovery"
down_revision = "018_workflow_execution"
branch_labels = None
depends_on = None

TABLES = (
    "demo_fixtures",
    "demo_observations",
    "evidence_documents",
    "evidence_sources",
    "evidence_bundles",
    "relay_signals",
    "relay_incidents",
    "relay_events",
    "relay_investigations",
    "relay_proposals",
    "relay_executions",
    "relay_verifications",
    "relay_capsules",
    "bench_capsule_replays",
    "evidence_links",
)
REFERENCES = {
    "demo_observations": {"target_id": "demo_fixtures"},
    "evidence_bundles": {"workflow_run_id": "workflow_runs"},
    "relay_signals": {"target_id": "demo_fixtures", "source_id": "evidence_sources"},
    "relay_incidents": {"target_id": "demo_fixtures", "signal_id": "relay_signals"},
    "relay_events": {"incident_id": "relay_incidents"},
    "relay_investigations": {
        "incident_id": "relay_incidents",
        "bundle_id": "evidence_bundles",
    },
    "relay_proposals": {
        "incident_id": "relay_incidents",
        "target_id": "demo_fixtures",
        "bundle_id": "evidence_bundles",
    },
    "relay_executions": {
        "incident_id": "relay_incidents",
        "proposal_id": "relay_proposals",
    },
    "relay_verifications": {
        "incident_id": "relay_incidents",
        "execution_id": "relay_executions",
        "target_id": "demo_fixtures",
        "observation_id": "demo_observations",
    },
    "relay_capsules": {
        "incident_id": "relay_incidents",
        "bundle_id": "evidence_bundles",
        "proposal_id": "relay_proposals",
        "verification_id": "relay_verifications",
    },
    "bench_capsule_replays": {"capsule_id": "relay_capsules"},
    "evidence_links": {"bundle_id": "evidence_bundles"},
}
UNIQUE = {
    "relay_incidents": ("organization_id", "project_id", "dedup_key"),
    "relay_events": ("incident_id", "sequence"),
    "relay_executions": ("organization_id", "project_id", "idempotency_key"),
    "evidence_links": ("bundle_id", "reference_kind", "reference_id"),
}
CONSTRAINT_NAMES = {
    "relay_incidents": "uq_relay_incident_key",
    "relay_events": "uq_relay_event_sequence",
    "relay_executions": "uq_relay_execution_key",
    "evidence_links": "uq_evidence_link",
}


def upgrade():
    connection = op.get_bind()
    for name in TABLES:
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
        for field, target in REFERENCES.get(name, {}).items():
            unique = (name, field) in {
                ("relay_executions", "proposal_id"),
                ("relay_verifications", "execution_id"),
                ("relay_capsules", "incident_id"),
            }
            columns.append(
                sa.Column(
                    field,
                    sa.String(64),
                    sa.ForeignKey(target + ".id"),
                    nullable=field == "workflow_run_id",
                    unique=unique,
                )
            )
        if name in {
            "evidence_documents",
            "evidence_sources",
            "evidence_bundles",
            "relay_incidents",
        }:
            columns.append(sa.Column("title", sa.String(160), nullable=False))
        if name == "evidence_sources":
            columns.append(sa.Column("blob", sa.LargeBinary(), nullable=False))
        if name in {"demo_fixtures", "relay_incidents"}:
            columns.append(sa.Column("revision", sa.Integer(), nullable=False))
        if name in {"evidence_bundles", "relay_incidents", "relay_executions"}:
            columns.append(sa.Column("status", sa.String(32), nullable=False))
        if name == "relay_events":
            columns.append(sa.Column("sequence", sa.Integer(), nullable=False))
        if name == "relay_incidents":
            columns.append(sa.Column("dedup_key", sa.String(128), nullable=False))
        if name == "relay_executions":
            columns.append(sa.Column("idempotency_key", sa.String(128), nullable=False))
        if name == "evidence_links":
            columns.extend(
                [
                    sa.Column("reference_kind", sa.String(32), nullable=False),
                    sa.Column("reference_id", sa.String(64), nullable=False),
                ]
            )
        if name in UNIQUE:
            columns.append(
                sa.UniqueConstraint(*UNIQUE[name], name=CONSTRAINT_NAMES[name])
            )
        op.create_table(name, *columns)
        op.create_index(
            "ix_" + name + "_scope",
            name,
            ["organization_id", "project_id", "created_at", "id"],
        )
    op.create_index("ix_relay_active_execution", "relay_executions", ["status"])
    op.create_index(
        "ix_relay_incident_status",
        "relay_incidents",
        ["organization_id", "project_id", "status"],
    )
    op.create_index(
        "ix_demo_observation_target", "demo_observations", ["target_id", "created_at"]
    )
    op.create_index(
        "ix_relay_event_incident", "relay_events", ["incident_id", "sequence"]
    )
    op.create_index(
        "ix_evidence_link_reference",
        "evidence_links",
        ["organization_id", "project_id", "reference_kind", "reference_id"],
    )
    install_intelligence_protection(connection, TABLES)


def downgrade():
    connection = op.get_bind()
    if any(
        connection.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar()
        for name in TABLES
    ):
        raise RuntimeError(
            "Populated intelligence history cannot be downgraded destructively."
        )
    for name in reversed(TABLES):
        op.drop_table(name)
