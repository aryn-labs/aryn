"""Single authority host coordination. OS lock lifetime is execution authority.

No timeout-based takeover: a blocked/live process keeps authority. PostgreSQL
additionally holds a session advisory lock, preventing a second host from starting.
"""
import hashlib
import os
from pathlib import Path
import threading
import uuid

from sqlalchemy import event, text


class ExecutionOwnershipError(RuntimeError):
    pass


class ExecutionAuthority:
    _guard = threading.RLock()
    _instances = {}

    @classmethod
    def for_engine(cls, engine):
        with cls._guard:
            current = getattr(engine, "_aryn_execution_authority", None)
            if current is not None:
                current.assert_valid()
                return current
            memory = engine.dialect.name == "sqlite" and engine.url.database in (None, "", ":memory:")
            key = ("memory", id(engine)) if memory else str(engine.url.set(password=None))
            if engine.dialect.name == "sqlite" and not memory:
                key = str(Path(engine.url.database).resolve())
            current = cls._instances.get(key)
            if current is None:
                current = cls(engine, memory)
                cls._instances[key] = current
            current.references += 1
            engine._aryn_execution_authority = current
            released = False
            @event.listens_for(engine, "engine_disposed")
            def release_authority(disposed):
                nonlocal released
                with cls._guard:
                    if released:
                        return
                    released = True
                    current.references -= 1
                    if current.references == 0:
                        current.close()
                        cls._instances.pop(key, None)
                    # Retain invalid object on a disposed engine: stale workers
                    # must never acquire a replacement authority transparently.
            return current

    def __init__(self, engine, memory):
        self._connection_guard = threading.RLock()
        self.owner_id = uuid.uuid4().hex
        self.valid, self.references, self.file, self.connection = True, 0, None, None
        if memory:
            return
        if engine.dialect.name == "sqlite":
            path = Path(str(Path(engine.url.database).resolve()) + ".execution.lock")
        else:
            root = os.getenv("ARYN_HISTORY_COMMITMENT_PATH")
            if not root:
                raise ExecutionOwnershipError("Protected authority host storage is required.")
            path = Path(root + ".execution.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if engine.dialect.name == "postgresql":
                self.connection = engine.connect()
                self.advisory_key = int.from_bytes(hashlib.sha256(b"aryn-core-execution").digest()[:8], "big", signed=True)
                if not self.connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": self.advisory_key}).scalar():
                    raise ExecutionOwnershipError("Another execution authority owns this database.")
                self.backend_pid = self.connection.execute(text("SELECT pg_backend_pid()")).scalar()
        except BaseException as exc:
            self.close()
            raise ExecutionOwnershipError("Execution authority is already active or unavailable.") from exc

    def assert_valid(self):
        with self._connection_guard:
            if not self.valid:
                raise ExecutionOwnershipError("Execution ownership was lost; stale worker is fenced.")
            if self.connection is not None:
                try:
                    if self.connection.invalidated or self.connection.execute(text("SELECT pg_backend_pid()")).scalar() != self.backend_pid:
                        raise ExecutionOwnershipError("Execution database lock was lost.")
                except Exception as exc:
                    self.valid = False
                    raise ExecutionOwnershipError("Execution database lock is unavailable.") from exc

    def close(self):
        with self._connection_guard:
            self.valid = False
            try:
                if self.connection is not None:
                    try:
                        if not self.connection.invalidated:
                            self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.advisory_key})
                    finally:
                        # A pooled session must not retain advisory ownership.
                        self.connection.invalidate()
                        self.connection.close()
                        self.connection = None
            finally:
                if self.file is not None:
                    self.file.close()
                    self.file = None
