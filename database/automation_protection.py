"""Non-erasable scheduler checkpoints and append-only scheduling decisions."""

from sqlalchemy import text

TABLES = ("automation_events",)
MUTABLE_TABLES = ("automation_definitions", "automation_occurrences")


def install_automation_protection(connection):
    for table in TABLES + MUTABLE_TABLES:
        if connection.dialect.name == "sqlite":
            for action in ("update", "delete") if table in TABLES else ("delete",):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Core scheduling evidence cannot be erased'); END"
                    )
                )
            conflict = "id=NEW.id"
            if table == "automation_occurrences":
                conflict += " OR (automation_id=NEW.automation_id AND occurrence_key=NEW.occurrence_key)"
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_insert BEFORE INSERT ON {table} WHEN EXISTS (SELECT 1 FROM {table} WHERE {conflict}) BEGIN SELECT RAISE(ABORT, 'Core scheduling evidence cannot be replaced'); END"
                )
            )
        elif connection.dialect.name == "postgresql":
            for action, name, level in (
                (
                    "UPDATE OR DELETE" if table in TABLES else "DELETE",
                    "mutation",
                    "ROW",
                ),
                ("TRUNCATE", "truncate", "STATEMENT"),
            ):
                connection.execute(
                    text(f"DROP TRIGGER IF EXISTS aryn_{table}_{name} ON {table}")
                )
                connection.execute(
                    text(
                        f"CREATE TRIGGER aryn_{table}_{name} BEFORE {action} ON {table} FOR EACH {level} EXECUTE FUNCTION aryn_reject_history_mutation()"
                    )
                )
            privileges = (
                "UPDATE, DELETE, TRUNCATE" if table in TABLES else "DELETE, TRUNCATE"
            )
            connection.execute(text(f"REVOKE {privileges} ON {table} FROM PUBLIC"))
