"""Append-only evidence and non-erasable disposable recovery checkpoints."""

from sqlalchemy import text

TABLES = (
    "demo_observations",
    "evidence_documents",
    "evidence_sources",
    "evidence_bundles",
    "relay_signals",
    "relay_events",
    "relay_investigations",
    "relay_proposals",
    "relay_verifications",
    "relay_capsules",
    "bench_capsule_replays",
    "evidence_links",
)
MUTABLE_TABLES = ("demo_fixtures", "relay_incidents", "relay_executions")
CONFLICTS = {
    "relay_events": "incident_id=NEW.incident_id AND sequence=NEW.sequence",
    "relay_verifications": "execution_id=NEW.execution_id",
    "relay_capsules": "incident_id=NEW.incident_id",
    "relay_incidents": "organization_id=NEW.organization_id AND project_id=NEW.project_id AND dedup_key=NEW.dedup_key",
    "relay_executions": "proposal_id=NEW.proposal_id OR (organization_id=NEW.organization_id AND project_id=NEW.project_id AND idempotency_key=NEW.idempotency_key)",
    "evidence_links": "bundle_id=NEW.bundle_id AND reference_kind=NEW.reference_kind AND reference_id=NEW.reference_id",
}


def install_intelligence_protection(connection, tables=None):
    for table in TABLES + MUTABLE_TABLES if tables is None else tables:
        if connection.dialect.name == "sqlite":
            actions = ("update", "delete") if table in TABLES else ("delete",)
            for action in actions:
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_{action} BEFORE {action} ON {table} "
                        "BEGIN SELECT RAISE(ABORT, 'Intelligence evidence cannot be erased or rewritten'); END"
                    )
                )
            conflict = CONFLICTS.get(table, "id=NEW.id")
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_insert BEFORE INSERT ON {table} "
                    f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id OR ({conflict})) "
                    "BEGIN SELECT RAISE(ABORT, 'Intelligence evidence cannot be replaced'); END"
                )
            )
        elif connection.dialect.name == "postgresql":
            mutation = "UPDATE OR DELETE" if table in TABLES else "DELETE"
            for action, name, level in (
                (mutation, "mutation", "ROW"),
                ("TRUNCATE", "truncate", "STATEMENT"),
            ):
                connection.execute(
                    text(f"DROP TRIGGER IF EXISTS aryn_{table}_{name} ON {table}")
                )
                connection.execute(
                    text(
                        f"CREATE TRIGGER aryn_{table}_{name} BEFORE {action} ON {table} "
                        f"FOR EACH {level} EXECUTE FUNCTION aryn_reject_history_mutation()"
                    )
                )
            privileges = (
                "UPDATE, DELETE, TRUNCATE" if table in TABLES else "DELETE, TRUNCATE"
            )
            connection.execute(text(f"REVOKE {privileges} ON {table} FROM PUBLIC"))
