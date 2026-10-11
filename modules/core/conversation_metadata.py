"""Own-user conversation metadata; deletion restricts access, never erases runs.

Append-only signed receipts and an independent freshness head prevent a database
rollback from resurrecting a deleted conversation. Admitted runs settle normally.
"""
import hashlib
import json
import uuid

from database.schema import ConversationChangeModel, ConversationModel, ProjectModel, utc_now
from modules.core.history import HistoryUnverifiedError, advance_head, receipt_head, verify_head
from packages.contracts.core import AuditStatus


class ConversationMetadata:
    def __init__(self, chat):
        self.chat, self.db = chat, chat.db

    @staticmethod
    def evidence(row):
        return {key: getattr(row, key) for key in (
            "id", "conversation_id", "organization_id", "project_id", "actor_id", "generation",
            "title", "deleted_at", "idempotency_key", "request_hash", "created_at")}

    def head(self, row):
        return receipt_head(row.id, row.generation, self.evidence(row)) if row else None

    def state(self, session, ctx, item):
        from modules.core.conversations import ChatError
        row = session.query(ConversationChangeModel).filter_by(conversation_id=item.id, **self.chat.scope(ctx)).order_by(
            ConversationChangeModel.generation.desc()).first()
        try:
            verify_head(session, "chat_metadata", ctx, item.id, self.head(row))
            if row and not self.db.evidence_signer.verify("chat_metadata", self.evidence(row), row.attestation):
                raise HistoryUnverifiedError("Conversation metadata differs.")
        except HistoryUnverifiedError:
            raise ChatError("conversation_metadata_unavailable", 503) from None
        return row

    def permissions(self, session, ctx):
        return {"can_rename": self.chat.core.permission_engine.evaluate("chat:update", ctx,
            ctx.organization_id, ctx.project_id, session=session).allowed,
            "can_delete": self.chat.core.permission_engine.evaluate("chat:delete", ctx,
            ctx.organization_id, ctx.project_id, session=session).allowed}

    def projection(self, item, row):
        return dict(id=item.id, organization_id=item.organization_id, project_id=item.project_id,
            title=row.title if row else item.title, metadata_revision=row.generation if row else 0,
            deleted=bool(row and row.deleted_at))

    def mutate(self, ctx, identifier, body, *, delete=False):
        from modules.core.conversations import ChatError
        action = "chat:delete" if delete else "chat:update"
        with self.db.session(write=True) as session:
            self.chat.authorize(ctx, session=session)
            self.chat.core.permission_engine.enforce(action, ctx, ctx.organization_id, ctx.project_id, session=session)
            # Serialize first claims across conversation IDs sharing an idempotency namespace.
            session.query(ProjectModel).filter_by(id=ctx.project_id, organization_id=ctx.organization_id).with_for_update().one()
            # Same row lock as turn admission: delete and admission have one ordering.
            item = session.query(ConversationModel).filter_by(id=identifier, **self.chat.scope(ctx)).with_for_update().first()
            if not item:
                raise ChatError("conversation_not_found", 404)
            previous = self.state(session, ctx, item)
            if previous and previous.deleted_at and not delete:
                raise ChatError("conversation_not_found", 404)
            fingerprint = hashlib.sha256(json.dumps({"conversation": identifier, "action": action,
                **body.model_dump()}, sort_keys=True).encode()).hexdigest()
            duplicate = session.query(ConversationChangeModel).filter_by(**self.chat.scope(ctx), idempotency_key=body.idempotency_key).first()
            if duplicate:
                if (duplicate.request_hash != fingerprint or not self.db.evidence_signer.verify(
                        "chat_metadata", self.evidence(duplicate), duplicate.attestation)):
                    raise ChatError("idempotency_conflict", 409)
                return self.projection(item, previous)
            # DELETE remains idempotent for a new request key too. Never append after a tombstone.
            if previous and previous.deleted_at:
                return self.projection(item, previous)
            generation = previous.generation if previous else 0
            if body.expected_metadata_revision != generation:
                raise ChatError("conversation_changed", 409)
            now = utc_now().isoformat()
            row = ConversationChangeModel(id="meta_" + uuid.uuid4().hex, conversation_id=identifier,
                **self.chat.scope(ctx), generation=generation + 1,
                title=(previous.title if previous else item.title) if delete else body.title,
                deleted_at=now if delete else None, idempotency_key=body.idempotency_key,
                request_hash=fingerprint, created_at=now)
            row.attestation = self.db.evidence_signer.sign("chat_metadata", self.evidence(row))
            session.add(row)
            advance_head(session, "chat_metadata", ctx, identifier, self.head(previous), self.head(row))
            self.chat.core.audit_logger.record("chat.conversation.deleted" if delete else "chat.conversation.renamed",
                ctx, identifier, AuditStatus.ALLOWED, {"metadata_revision": row.generation,
                "retention": "execution_evidence_retained"} if delete else {"metadata_revision": row.generation}, session=session)
            return self.projection(item, row)
