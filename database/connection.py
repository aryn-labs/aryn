"""Database connection and session management for ARYN infrastructure.

Supports SQLite for local development and PostgreSQL Cloud.
Enforces foreign keys on SQLite connections.
"""

from __future__ import annotations
import os
import sqlite3
import threading
from contextlib import contextmanager, nullcontext
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from database.schema import Base

DEFAULT_SQLITE_URL = "sqlite:///aryn_local.db"


def get_database_url() -> str:
    return os.getenv("ARYN_DATABASE_URL", DEFAULT_SQLITE_URL)


def create_db_engine(url: str | None = None, echo: bool = False) -> Engine:
    db_url = url or get_database_url()

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(db_url, echo=echo, connect_args=connect_args)

    # Enforce SQLite foreign key constraints
    if db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            # An arbitrary SQL writer on an application connection must not
            # acquire the authority process's access to the independent store or
            # key through ATTACH/VACUUM INTO or file/extension SQL functions.
            connection_record.info["aryn_sql_mutations"] = 0
            read_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT, sqlite3.SQLITE_RECURSIVE}
            def restrict_authority_files(action, argument, detail, database, source):
                if action not in read_actions:
                    connection_record.info["aryn_sql_mutations"] += 1
                if action == sqlite3.SQLITE_ATTACH:
                    return sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_FUNCTION and (detail or "").lower() in {"load_extension", "readfile", "writefile"}:
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection_record.info["aryn_sql_authorizer"] = restrict_authority_files
            dbapi_connection.set_authorizer(restrict_authority_files)

    return engine


def init_db(engine: Engine) -> None:
    """Initializes tables in database."""
    Base.metadata.create_all(bind=engine)


def check_db_health(engine: Engine) -> bool:
    """Verifies database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


class DatabaseManager:
    """Singleton-like or contextual manager for DB sessions."""

    _history_lock = threading.RLock()

    def __init__(self, engine: Engine | None = None, evidence_signer=None) -> None:
        self.engine = engine or create_db_engine()
        self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._evidence_signer = evidence_signer or getattr(self.engine, "_aryn_evidence_signer", None)
        if evidence_signer is not None and not hasattr(self.engine, "_aryn_evidence_signer"):
            self.engine._aryn_evidence_signer = evidence_signer
        self.permission_engine = getattr(self.engine, "_aryn_permission_engine", None)
        self.approval_authority = getattr(self.engine, "_aryn_approval_authority", None)
        # A local reader must see the DB row and independent history head from
        # the same completed transaction. Share the lock across managers using
        # this engine, including reads, before taking SQLite's writer lock.
        with self._history_lock:
            if self.engine.dialect.name == "sqlite" and not hasattr(self.engine, "_aryn_session_lock"):
                self.engine._aryn_session_lock = threading.RLock()

    @property
    def evidence_signer(self):
        from modules.core.evidence import EvidenceSigner
        with self._history_lock:
            if self._evidence_signer is None:
                self._evidence_signer = getattr(self.engine, "_aryn_evidence_signer", None) or EvidenceSigner.for_database(self.engine)
                self.engine._aryn_evidence_signer = self._evidence_signer
        return self._evidence_signer

    @property
    def history_commitments(self):
        from modules.core.history import HistoryCommitments
        with self._history_lock:
            if not hasattr(self.engine, "_aryn_history_commitments"):
                self.engine._aryn_history_commitments = HistoryCommitments(self.engine, self.evidence_signer)
            return self.engine._aryn_history_commitments

    @contextmanager
    def session(self, write: bool = False) -> Generator[Session, None, None]:
        # Never hold a session across an await or external I/O. This SQLite boundary
        # includes prepare/commit/finish; abandoned durable intents still fail
        # closed through the unchanged independent commitment verification.
        with getattr(self.engine, "_aryn_session_lock", nullcontext()):
            with self._session(write) as session:
                yield session

    @contextmanager
    def _session(self, write: bool) -> Generator[Session, None, None]:
        session: Session = self.session_factory()
        session.info["write"] = write
        session.info["db_manager"] = self
        tracked_connection = None
        initial_changes = None
        initial_mutations = None
        effectful_statement = False
        def observe_statement(connection, cursor, statement, parameters, context, executemany):
            nonlocal effectful_statement
            # Only optimize demonstrably read-only SQLite transactions. Unknown
            # SQL, DDL and every DML statement retain the durable intent protocol.
            if not statement.lstrip().upper().startswith(("SELECT ", "BEGIN ")):
                effectful_statement = True
        @event.listens_for(session, "after_rollback")
        def discard_staged_commitment(rolled_back_session):
            for key in ("history_observations", "history_updates", "new_assignment_ids", "publishing_version_id"):
                rolled_back_session.info.pop(key, None)
        try:
            if self.engine.dialect.name == "sqlite":
                tracked_connection = session.connection()
                raw = tracked_connection.connection.driver_connection
                # Resetting the authorizer expires cached prepared statements,
                # including SQL executed by callbacks through the raw driver.
                authorizer = tracked_connection.info.get("aryn_sql_authorizer")
                if callable(authorizer):
                    raw.set_authorizer(authorizer)
                    initial_mutations = tracked_connection.info["aryn_sql_mutations"]
                initial_changes = raw.total_changes
                event.listen(tracked_connection, "before_cursor_execute", observe_statement)
            if write and self.engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.flush()
            observations = session.info.get("history_observations", {})
            token = None
            updates = session.info.get("history_updates", {})
            if session.info.get("write") and observations:
                read_only = (tracked_connection is not None and initial_mutations is not None and not effectful_statement
                    and tracked_connection.connection.driver_connection.total_changes == initial_changes
                    and tracked_connection.info["aryn_sql_mutations"] == initial_mutations)
                if updates or not read_only:
                    token = self.history_commitments.prepare(observations, updates)
                    session.commit()
                else:
                    with self.history_commitments.guard_observations(observations):
                        session.commit()
            else:
                session.commit()
            if token:
                self.history_commitments.finish(token)
        except Exception:
            session.rollback()
            raise
        finally:
            if tracked_connection is not None:
                event.remove(tracked_connection, "before_cursor_execute", observe_statement)
            session.close()
