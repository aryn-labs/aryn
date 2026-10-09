"""Scoped records using existing Core permissions, signatures and protected heads."""

import json
import datetime
from sqlalchemy import and_, or_
from database.repositories.exceptions import EntityNotFoundError
from modules.core.history import advance_head, verify_head, HistoryUnverifiedError
from modules.core.workflows.executor import encoded, digest, identity, now
from packages.contracts.core import AuditStatus


class SignedRecords:
    def __init__(self, core):
        self.core = core
        self.db = core.db_manager
        self.permissions = core.permission_engine

    def authorize(self, session, ctx, action="run:read"):
        self.permissions.enforce(
            action, ctx, ctx.organization_id, ctx.project_id, session=session
        )

    def clean(self, value):
        from modules.core.errors import sanitize

        return sanitize(
            value, credentials=getattr(self.db, "protected_credentials", ())
        )

    def get(self, session, cls, ctx, identifier, lock=False):
        self.authorize(session, ctx)
        return self._verified(session, cls, ctx, identifier, lock)

    def _verified(self, session, cls, ctx, identifier, lock=False):
        query = session.query(cls).filter_by(
            id=identifier,
            organization_id=ctx.organization_id,
            project_id=ctx.project_id,
        )
        row = (
            query.with_for_update().populate_existing().first()
            if lock
            else query.first()
        )
        if row is None:
            raise EntityNotFoundError("Scoped evidence resource unavailable.")
        try:
            payload = json.loads(row.details_json)
        except (ValueError, TypeError) as exc:
            raise HistoryUnverifiedError("Record payload is unreadable.") from exc
        from packages.contracts.timestamps import canonical_timestamp

        try:
            timestamp_matches = isinstance(payload, dict) and canonical_timestamp(row.created_at, stored=True) == canonical_timestamp(payload["created_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoryUnverifiedError("Record timestamp is unreadable.") from exc
        if not timestamp_matches:
            raise HistoryUnverifiedError(
                "Record timestamp differs from signed evidence."
            )
        for field in cls.__table__.columns.keys():
            if field not in {"details_json", "attestation", "created_at", "blob"}:
                if payload.get(field) != getattr(row, field):
                    raise HistoryUnverifiedError(
                        "Record scope or indexed relationship differs."
                    )
        if not self.db.evidence_signer.verify(
            cls.__tablename__, payload, row.attestation
        ):
            raise HistoryUnverifiedError("Record signature is unverified.")
        verify_head(
            session, cls.__tablename__, ctx, identifier, {"digest": digest(payload)}
        )
        return row, payload

    def put(self, session, ctx, row, payload, new=False):
        self.core._fence()
        previous = None if new else {"digest": digest(json.loads(row.details_json))}
        advance_head(
            session,
            row.__tablename__,
            ctx,
            row.id,
            previous,
            {"digest": digest(payload)},
        )
        for field in row.__table__.columns.keys():
            if field not in {"details_json", "attestation", "created_at", "blob"}:
                setattr(row, field, payload[field])
        row.details_json = encoded(payload).decode()
        row.attestation = self.db.evidence_signer.sign(row.__tablename__, payload)
        if new:
            row.created_at = datetime.datetime.fromisoformat(payload["created_at"])
            session.add(row)
        session.flush()

    def add(self, session, ctx, cls, record_type, prefix, blob=None, **fields):
        payload = record_type.model_validate(
            {
                "id": identity(prefix),
                "organization_id": ctx.organization_id,
                "project_id": ctx.project_id,
                "created_at": now(),
                **fields,
            }
        ).model_dump(mode="json")
        for hash_field in ("digest", "payload_hash"):
            if payload.get(hash_field) == "0" * 64:
                payload[hash_field] = digest(
                    {key: value for key, value in payload.items() if key != hash_field}
                )
        row = cls(
            id=payload["id"],
            organization_id=ctx.organization_id,
            project_id=ctx.project_id,
            **({"blob": blob} if blob is not None else {}),
        )
        self.put(session, ctx, row, payload, True)
        return row, payload

    def audit(self, session, ctx, event, subject, **details):
        self.core.audit_logger.record(
            event, ctx, subject, AuditStatus.COMPLETED, details, session=session
        )

    def page(self, session, ctx, cls, after="", limit=25, q="", status="", **filters):
        self.authorize(session, ctx)
        query = session.query(cls).filter_by(
            organization_id=ctx.organization_id, project_id=ctx.project_id, **filters
        )
        if status:
            query = query.filter_by(status=status)
        if q:
            literal = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.filter(cls.title.ilike("%" + literal + "%", escape="\\"))
        if after:
            cursor, _ = self.get(session, cls, ctx, after)
            if any(getattr(cursor, key) != value for key, value in filters.items()):
                raise EntityNotFoundError("Pagination scope differs.")
            query = query.filter(
                or_(
                    cls.created_at < cursor.created_at,
                    and_(cls.created_at == cursor.created_at, cls.id < cursor.id),
                )
            )
        rows = (
            query.order_by(cls.created_at.desc(), cls.id.desc()).limit(limit + 1).all()
        )
        return [self.get(session, cls, ctx, row.id)[1] for row in rows[:limit]], rows[
            limit - 1
        ].id if len(rows) > limit else None
