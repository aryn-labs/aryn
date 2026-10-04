"""Internal attestations for persisted governance evidence, never issued by the API."""

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path


class EvidenceSigner:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("Evidence signing key must contain at least 32 bytes.")
        self._key = key

    @classmethod
    def for_database(cls, engine):
        configured = os.getenv("ARYN_EVIDENCE_SECRET")
        if configured:
            return cls(configured.encode("utf-8"))
        if engine.url.get_backend_name() != "sqlite":
            raise ValueError("Persistent governance evidence requires ARYN_EVIDENCE_SECRET.")
        database = engine.url.database
        if not database or database == ":memory:":
            return cls(secrets.token_bytes(32))
        path = Path(database).resolve().with_suffix(".aryn-evidence.key")
        if not path.exists():
            # Install a complete random key atomically; concurrent processes reuse the winner.
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".aryn-key-")
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(secrets.token_bytes(32))
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
            finally:
                Path(temporary).unlink(missing_ok=True)
        return cls(path.read_bytes())

    def sign(self, kind: str, payload: dict) -> str:
        message = json.dumps({"kind": kind, "payload": payload}, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def verify(self, kind: str, payload: dict, signature: str) -> bool:
        return bool(signature) and hmac.compare_digest(self.sign(kind, payload), signature)
