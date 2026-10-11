"""Append-only idempotency evidence; project deletion is not a Studio capability."""
from sqlalchemy import text


def install_project_protection(connection):
    if connection.dialect.name == "sqlite":
        for action in ("update", "delete"):
            connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS aryn_project_mutations_{action} BEFORE {action} ON project_mutations BEGIN SELECT RAISE(ABORT, 'Project receipts are append-only'); END"))
        connection.execute(text("CREATE TRIGGER IF NOT EXISTS aryn_project_mutations_insert BEFORE INSERT ON project_mutations WHEN EXISTS (SELECT 1 FROM project_mutations WHERE id=NEW.id OR (organization_id=NEW.organization_id AND actor_id=NEW.actor_id AND idempotency_key=NEW.idempotency_key)) BEGIN SELECT RAISE(ABORT, 'Project receipts are append-only'); END"))
    elif connection.dialect.name == "postgresql":
        connection.execute(text("CREATE OR REPLACE FUNCTION aryn_reject_project_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Project receipts are append-only'; END; $$"))
        for action, level, name in (("UPDATE OR DELETE", "ROW", "mutation"), ("TRUNCATE", "STATEMENT", "truncate")):
            connection.execute(text(f"DROP TRIGGER IF EXISTS aryn_project_mutations_{name} ON project_mutations"))
            connection.execute(text(f"CREATE TRIGGER aryn_project_mutations_{name} BEFORE {action} ON project_mutations FOR EACH {level} EXECUTE FUNCTION aryn_reject_project_mutation()"))
        connection.execute(text("REVOKE UPDATE, DELETE, TRUNCATE ON project_mutations FROM PUBLIC"))
