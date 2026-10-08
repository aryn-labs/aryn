"""Database connection and session management for ARYN infrastructure.

Supports SQLite for local development and PostgreSQL Cloud.
Enforces foreign keys on SQLite connections.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
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
            def restrict_authority_files(action, argument, detail, database, source):
                if action == sqlite3.SQLITE_ATTACH:
                    return sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_FUNCTION and (detail or "").lower() in {"load_extension", "readfile", "writefile"}:
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
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
        self._evidence_signer = evidence_signer

    @property
    def evidence_signer(self):
        from modules.core.evidence import EvidenceSigner
        if self._evidence_signer is None:
            self._evidence_signer = EvidenceSigner.for_database(self.engine)
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
        session: Session = self.session_factory()
        session.info["write"] = write
        session.info["db_manager"] = self
        @event.listens_for(session, "after_rollback")
        def discard_staged_commitment(rolled_back_session):
            for key in ("history_observations", "history_updates", "new_assignment_ids", "publishing_version_id"):
                rolled_back_session.info.pop(key, None)
        try:
            if write and self.engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.flush()
            observations = session.info.get("history_observations", {})
            token = None
            if session.info.get("write") and observations:
                token = self.history_commitments.prepare(observations, session.info.get("history_updates", {}))
            session.commit()
            if token:
                self.history_commitments.finish(token)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
