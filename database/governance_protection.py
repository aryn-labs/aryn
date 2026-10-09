"""Database-level append-only enforcement, shared by metadata and migrations."""
from sqlalchemy import text

HISTORY_TABLES = ("agent_publications", "assignment_transitions", "bench_baselines", "bench_comparisons", "audit_events")


def install_history_protection(connection):
    if connection.dialect.name == "sqlite":
        conflicts = {
            "agent_publications": "version_id=NEW.version_id",
            "assignment_transitions": "assignment_id=NEW.assignment_id AND (generation=NEW.generation OR idempotency_key=NEW.idempotency_key)",
            "bench_baselines": "organization_id=NEW.organization_id AND project_id=NEW.project_id AND blueprint_id=NEW.blueprint_id AND generation=NEW.generation",
            "audit_events": "event_id=NEW.event_id",
        }
        for table in HISTORY_TABLES:
            for action in ("UPDATE", "DELETE"):
                connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_{action.lower()} "
                    f"BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Governance history is append-only'); END"))
            # REPLACE implicitly deletes conflicting rows without firing DELETE
            # triggers when recursive_triggers is disabled. Reject every unique
            # conflict before the insert, including alternate unique identities.
            conflict = conflicts.get(table, "id=NEW.id")
            connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS aryn_{table}_insert BEFORE INSERT ON {table} "
                f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id OR ({conflict})) "
                "BEGIN SELECT RAISE(ABORT, 'Governance history is append-only'); END"))
    elif connection.dialect.name == "postgresql":
        connection.execute(text("CREATE OR REPLACE FUNCTION aryn_reject_history_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Governance history is append-only'; END; $$"))
        for table in HISTORY_TABLES:
            connection.execute(text(f"DROP TRIGGER IF EXISTS aryn_{table}_mutation ON {table}"))
            connection.execute(text(f"DROP TRIGGER IF EXISTS aryn_{table}_truncate ON {table}"))
            connection.execute(text(f"CREATE TRIGGER aryn_{table}_mutation BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION aryn_reject_history_mutation()"))
            connection.execute(text(f"CREATE TRIGGER aryn_{table}_truncate BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION aryn_reject_history_mutation()"))
            connection.execute(text(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC"))


def remove_history_protection(connection):
    for table in HISTORY_TABLES:
        if connection.dialect.name == "sqlite":
            for action in ("update", "delete", "insert"):
                connection.execute(text(f"DROP TRIGGER IF EXISTS aryn_{table}_{action}"))
        elif connection.dialect.name == "postgresql":
            for action in ("mutation", "truncate"):
                connection.execute(text(f"DROP TRIGGER IF EXISTS aryn_{table}_{action} ON {table}"))
    if connection.dialect.name == "postgresql":
        connection.execute(text("DROP FUNCTION IF EXISTS aryn_reject_history_mutation()"))


def verify_hosted_writer(engine):
    """Reject a hosted application role capable of bypassing append-only DDL.

    This is a deployment prerequisite check, not proof against superuser/host
    compromise. Provision schema with a separate migration owner.
    """
    if engine.dialect.name != "postgresql":
        return
    from modules.core.history import HistoryUnverifiedError
    with engine.connect() as connection:
        unsafe = connection.execute(text("SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user")).scalar()
        unsafe = unsafe or connection.execute(text("SELECT has_schema_privilege(current_user, current_schema(), 'CREATE')")).scalar()
        unsafe = unsafe or connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN "
            "('pg_read_server_files','pg_write_server_files','pg_execute_server_program') "
            "AND pg_has_role(current_user, oid, 'MEMBER'))")).scalar()
        from sqlalchemy import inspect
        from database.workflow_protection import TABLES, MUTABLE_TABLES
        protected = HISTORY_TABLES + tuple(table for table in TABLES + MUTABLE_TABLES if table in inspect(connection).get_table_names())
        for table in protected:
            privileges = "DELETE,TRUNCATE,TRIGGER" if table in MUTABLE_TABLES else "UPDATE,DELETE,TRUNCATE,TRIGGER"
            unsafe = unsafe or connection.execute(text(f"SELECT has_table_privilege(current_user, :table, '{privileges}') "
                "OR pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid=CAST(:table AS regclass)), 'MEMBER')"),
                {"table": table}).scalar()
            enabled = connection.execute(text("SELECT COUNT(*) FROM pg_trigger WHERE tgrelid=CAST(:table AS regclass) "
                "AND tgname IN (:mutation, :truncate) AND tgenabled IN ('O','A')"),
                {"table": table, "mutation": f"aryn_{table}_mutation", "truncate": f"aryn_{table}_truncate"}).scalar()
            unsafe = unsafe or enabled != 2
        if unsafe:
            raise HistoryUnverifiedError("Hosted governance requires a non-owner restricted database writer and enabled history guards.")
