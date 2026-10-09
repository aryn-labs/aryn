"""Append-only artifacts, graph versions and human decisions across both stores."""

from sqlalchemy import text

TABLES = ("workflow_versions", "workflow_artifacts", "workflow_deliverables")
MUTABLE_TABLES = ("workflow_definitions", "workflow_runs")


def install_workflow_protection(connection):
    for table in TABLES:
        if connection.dialect.name == "sqlite":
            for action in ("update", "delete"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_{action} BEFORE {action} ON {table} "
                        "BEGIN SELECT RAISE(ABORT, 'Workflow evidence is append-only'); END"
                    )
                )
            conflict = (
                "workflow_id=NEW.workflow_id AND revision=NEW.revision"
                if table == "workflow_versions"
                else "workflow_run_id=NEW.workflow_run_id"
                if table == "workflow_deliverables"
                else "id=NEW.id"
            )
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_insert BEFORE INSERT ON {table} "
                    f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id OR ({conflict})) "
                    "BEGIN SELECT RAISE(ABORT, 'Workflow evidence is append-only'); END"
                )
            )
        elif connection.dialect.name == "postgresql":
            for action, level in (
                ("UPDATE OR DELETE", "ROW"),
                ("TRUNCATE", "STATEMENT"),
            ):
                name = "truncate" if action == "TRUNCATE" else "mutation"
                connection.execute(
                    text(f"DROP TRIGGER IF EXISTS aryn_{table}_{name} ON {table}")
                )
                connection.execute(
                    text(
                        f"CREATE TRIGGER aryn_{table}_{name} BEFORE {action} ON {table} "
                        f"FOR EACH {level} EXECUTE FUNCTION aryn_reject_history_mutation()"
                    )
                )
            connection.execute(
                text(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC")
            )
    # Signed checkpoints remain updateable by Core, but deletion/REPLACE cannot
    # erase an idempotency claim or make interrupted effects appear never started.
    for table in MUTABLE_TABLES:
        if connection.dialect.name == "sqlite":
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_delete BEFORE DELETE ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'Workflow checkpoints cannot be erased'); END"
                )
            )
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_insert BEFORE INSERT ON {table} "
                    f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id) "
                    "BEGIN SELECT RAISE(ABORT, 'Workflow checkpoints cannot be replaced'); END"
                )
            )
        elif connection.dialect.name == "postgresql":
            for action, level, name in (
                ("DELETE", "ROW", "mutation"),
                ("TRUNCATE", "STATEMENT", "truncate"),
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
            connection.execute(text(f"REVOKE DELETE, TRUNCATE ON {table} FROM PUBLIC"))
