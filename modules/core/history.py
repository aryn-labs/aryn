"""Independent durable freshness commitments for the existing governance receipts.

The application database writer must not have filesystem access to this store or
the signing key. Local SQLite supports database-only corruption, not a hostile
host/file owner. A pending commit is deliberately never recovered from DB rows.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from packages.contracts.agent import VersionIntegrityError


class HistoryUnverifiedError(VersionIntegrityError):
    pass


def head_key(kind, context, subject):
    return json.dumps([kind, context.organization_id, context.project_id, subject], separators=(",", ":"))


def receipt_head(identity, generation, payload):
    from packages.contracts.bench import evidence_hash
    return {"identity": identity, "generation": generation, "hash": evidence_hash(payload)}


class HistoryCommitments:
    """A separate authority store; authenticated whole state detects lost entries.

    SQLite FULL synchronous transactions serialize processes. A durable pending
    intent precedes application DB commit, then is finalized after its ACK. Crash
    or ambiguous ACK leaves pending and denies governance until operator recovery
    from independently retained evidence. There is no automatic DB-based reset.
    """

    def __init__(self, engine, signer):
        from database.governance_protection import verify_hosted_writer
        verify_hosted_writer(engine)
        self.signer = signer
        self.lock = threading.RLock()
        self.path = None
        database = engine.url.database
        identity = str(Path(database).resolve()) if engine.dialect.name == "sqlite" and database and database != ":memory:" else engine.url.render_as_string(hide_password=True)
        self.namespace = hashlib.sha256(identity.encode()).hexdigest()
        configured = os.getenv("ARYN_HISTORY_COMMITMENT_PATH")
        if engine.dialect.name == "sqlite" and (not database or database == ":memory:"):
            self.memory = self.initial()
            return
        if configured:
            self.path = Path(configured).resolve()
        elif engine.dialect.name == "sqlite":
            self.path = Path(database).resolve().with_suffix(".aryn-history.sqlite3")
        else:
            # Hosted deployments must explicitly provide protected durable storage.
            raise HistoryUnverifiedError("ARYN_HISTORY_COMMITMENT_PATH is required outside the application database.")
        if engine.dialect.name == "sqlite" and self.path == Path(database).resolve():
            raise HistoryUnverifiedError("History commitment must be independent of the application database.")
        anchor = self.path.with_suffix(self.path.suffix + ".initialized")
        if anchor.exists():
            try:
                anchor_signature = anchor.read_text()
            except (OSError, ValueError) as exc:
                raise HistoryUnverifiedError("Independent history anchor cannot be read.") from exc
            if not self.path.exists() or anchor_signature != self.signer.sign("history_store", {"namespace": self.namespace}):
                raise HistoryUnverifiedError("Independent history commitment is missing or its anchor differs.")
        else:
            # O_EXCL prevents reinitializing an existing or partially created store.
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                with self.connect() as connection:
                    connection.execute("CREATE TABLE commitment (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL, signature TEXT NOT NULL)")
                    document = self.initial()
                    connection.execute("INSERT INTO commitment VALUES (1, ?, ?)", self.encode(document))
                with anchor.open("x") as stream:
                    stream.write(self.signer.sign("history_store", {"namespace": self.namespace}))
                    stream.flush()
                    os.fsync(stream.fileno())
            except (OSError, sqlite3.Error) as exc:
                raise HistoryUnverifiedError("History store cannot be initialized; no automatic replacement is allowed.") from exc
        self.read()  # Validate the complete store, including durable pending intent.

    def initial(self):
        return {"format": 1, "namespace": self.namespace, "sequence": 0, "heads": {}, "pending": None}

    @contextmanager
    def connect(self):
        if not self.path.exists():
            raise HistoryUnverifiedError("Independent history store is missing.")
        connection = sqlite3.connect(f"{self.path.as_uri()}?mode=rw", uri=True, timeout=30)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
        finally:
            connection.close()

    def encode(self, document):
        return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False), self.signer.sign("history_commitment", document)

    def decode(self, row):
        if row is None:
            raise HistoryUnverifiedError("Independent history state is missing.")
        document = json.loads(row[0])
        if (document["namespace"] != self.namespace or document["format"] != 1
                or not self.signer.verify("history_commitment", document, row[1])):
            raise HistoryUnverifiedError("Independent history state authentication failed.")
        return document

    def read(self):
        try:
            with self.lock:
                if self.path is None:
                    document = json.loads(json.dumps(self.memory))
                else:
                    with self.connect() as connection:
                        document = self.decode(connection.execute("SELECT document, signature FROM commitment WHERE id=1").fetchone())
                if document["pending"] is not None:
                    raise HistoryUnverifiedError("History commitment has an unresolved durable commit intent.")
                return document
        except HistoryUnverifiedError:
            raise
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            raise HistoryUnverifiedError("Independent history commitment cannot be verified.") from exc

    def mutate(self, change):
        try:
            with self.lock:
                if self.path is None:
                    document = json.loads(json.dumps(self.memory))
                    change(document)
                    self.memory = document
                else:
                    with self.connect() as connection:
                        connection.execute("BEGIN IMMEDIATE")
                        document = self.decode(connection.execute("SELECT document, signature FROM commitment WHERE id=1").fetchone())
                        change(document)
                        connection.execute("UPDATE commitment SET document=?, signature=? WHERE id=1", self.encode(document))
        except HistoryUnverifiedError:
            raise
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            raise HistoryUnverifiedError("Independent history commitment write failed.") from exc

    def prepare(self, observations, updates):
        token = uuid.uuid4().hex
        def change(document):
            if document["pending"] is not None or any(document["heads"].get(k) != v for k, v in observations.items()):
                raise HistoryUnverifiedError("History freshness changed before database commit.")
            document["pending"] = {"token": token, "updates": updates, "sequence": document["sequence"] + 1}
        self.mutate(change)
        return token

    def finish(self, token):
        def change(document):
            pending = document["pending"]
            if pending is None or pending["token"] != token:
                raise HistoryUnverifiedError("History commit intent differs.")
            document["heads"].update(pending["updates"])
            document["sequence"] = pending["sequence"]
            document["pending"] = None
        self.mutate(change)


def authority(session):
    manager = session.info.get("db_manager")
    if manager is None:
        raise HistoryUnverifiedError("History requires the configured governance transaction authority.")
    return manager.history_commitments


def observed_head(session, kind, context, subject):
    key = head_key(kind, context, subject)
    document = authority(session).read()
    current = document["heads"].get(key)
    observations = session.info.setdefault("history_observations", {})
    if key in observations and observations[key] != current:
        raise HistoryUnverifiedError("History changed during governance verification.")
    observations[key] = current
    return session.info.get("history_updates", {}).get(key, current)


def verify_head(session, kind, context, subject, expected):
    if observed_head(session, kind, context, subject) != expected:
        raise HistoryUnverifiedError("History head is missing, stale or does not match the independent commitment.")


def advance_head(session, kind, context, subject, expected, updated):
    session.info["write"] = True
    verify_head(session, kind, context, subject, expected)
    session.info.setdefault("history_updates", {})[head_key(kind, context, subject)] = updated
