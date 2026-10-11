"""Database guards for conversation rename/delete receipts; never purge evidence."""
from sqlalchemy import text

TABLES = ("chat_conversation_changes",)


def install_chat_protection(connection):
    for table in TABLES:
        if connection.dialect.name == "sqlite":
            for action in ("update", "delete"):
                connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_{action} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'Conversation metadata is append-only'); END"))
            connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_insert BEFORE INSERT ON {table} "
                f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id OR (conversation_id=NEW.conversation_id AND generation=NEW.generation) "
                "OR (organization_id=NEW.organization_id AND project_id=NEW.project_id AND actor_id=NEW.actor_id AND idempotency_key=NEW.idempotency_key)) "
                "BEGIN SELECT RAISE(ABORT, 'Conversation metadata is append-only'); END"))
        elif connection.dialect.name == "postgresql":
            for action, level, name in (("UPDATE OR DELETE", "ROW", "mutation"), ("TRUNCATE", "STATEMENT", "truncate")):
                connection.execute(text(f"DROP TRIGGER IF EXISTS aryn_{table}_{name} ON {table}"))
                connection.execute(text(f"CREATE TRIGGER aryn_{table}_{name} BEFORE {action} ON {table} "
                    f"FOR EACH {level} EXECUTE FUNCTION aryn_reject_history_mutation()"))
            connection.execute(text(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC"))
