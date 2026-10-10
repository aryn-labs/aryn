"""Personal chat settings. Browser flags never grant remote-transfer authority."""
import hashlib
import uuid

from database.schema import ProviderConsentModel, StudioPreferenceModel, utc_now
from packages.contracts.core import AuditStatus
from modules.core.history import verify_head, advance_head, receipt_head, HistoryUnverifiedError

POLICY_VERSION = "text-chat-v1:full-transcript:metered-readiness:no-tools"


class ChatSettings:
    def __init__(self, conversations):
        self.chat = conversations
        self.db = conversations.db

    def provider(self, model):
        # A loopback gateway does NOT establish local inference. Current Hermes/9Router
        # discovery cannot attest a local-only route; all such routes require consent.
        gateway = getattr(self.chat.core.runtime_adapter, "model_gateway", None)
        settings = getattr(gateway, "settings", None)
        endpoint = getattr(settings, "base_url", "configured-runtime")
        route = model.split("/", 1)[0] if "/" in model else "configured-model"
        provider_id = hashlib.sha256(f"{endpoint}|{route}".encode()).hexdigest()
        policy = hashlib.sha256(f"{provider_id}|{POLICY_VERSION}".encode()).hexdigest()
        return dict(provider_id=provider_id, name=route, policy=policy, remote=True)

    @staticmethod
    def evidence(row):
        return {key: getattr(row, key) for key in (
            "id", "organization_id", "project_id", "actor_id", "provider_id",
            "policy", "granted_at", "revoked_at")}

    def valid(self, session, ctx, provider, lock=False):
        query = session.query(ProviderConsentModel).filter_by(**self.chat.scope(ctx), provider_id=provider["provider_id"])
        row = (query.with_for_update() if lock else query).first()
        self.verify(session, ctx, provider["provider_id"], row)
        return bool(row and row.policy == provider["policy"] and not row.revoked_at
            and self.db.evidence_signer.verify("chat_provider_consent", self.evidence(row), row.attestation))

    def head(self, row):
        return receipt_head(row.id, row.granted_at + "|" + (row.revoked_at or ""), self.evidence(row)) if row else None

    def verify(self, session, ctx, provider_id, row):
        from modules.core.conversations import ChatError
        try:
            verify_head(session, "chat_consent", ctx, ctx.actor.actor_id + ":" + provider_id, self.head(row))
            if row and not self.db.evidence_signer.verify("chat_provider_consent", self.evidence(row), row.attestation):
                raise HistoryUnverifiedError("Consent evidence differs.")
        except HistoryUnverifiedError:
            raise ChatError("consent_history_unavailable", 503) from None

    def require(self, ctx, model, session=None):
        from modules.core.conversations import ChatError
        provider = self.provider(model)
        if session is None:
            with self.db.session() as current:
                return self.require(ctx, model, current)
        if not self.valid(session, ctx, provider, lock=bool(session.info.get("write"))):
            raise ChatError("remote_consent_required", 422)

    async def policies(self, ctx):
        self.chat.authorize(ctx)
        discovery = await self.chat.catalog()
        with self.db.session() as session:
            self.chat.authorize(ctx, session=session)
            providers, receipts = {}, {}
            for model in discovery.models:
                provider = self.provider(model["model_id"])
                if provider["provider_id"] not in receipts:
                    receipts[provider["provider_id"]] = self.valid(session, ctx, provider)
                provider["consented"] = receipts[provider["provider_id"]]
                providers[model["model_id"]] = provider
            return dict(**self.chat.scope(ctx), models=providers)

    async def grant(self, ctx, body):
        from modules.core.conversations import ChatError
        self.chat.authorize(ctx, write=True)
        discovery = await self.chat.catalog()
        if not any(m["model_id"] == body.model for m in discovery.models):
            raise ChatError("model_unavailable", 422)
        provider = self.provider(body.model)
        if body.policy != provider["policy"]:
            raise ChatError("consent_policy_changed", 409)
        with self.db.session(write=True) as session:
            self.chat.authorize(ctx, write=True, session=session)
            # Serialize settings changes per existing project row, including first grants.
            from database.schema import ProjectModel
            session.query(ProjectModel).filter_by(id=ctx.project_id, organization_id=ctx.organization_id).with_for_update().one()
            row = session.query(ProviderConsentModel).filter_by(**self.chat.scope(ctx), provider_id=provider["provider_id"]).with_for_update().first()
            self.verify(session, ctx, provider["provider_id"], row)
            previous = self.head(row)
            if not row:
                row = ProviderConsentModel(id="consent_" + uuid.uuid4().hex, **self.chat.scope(ctx), provider_id=provider["provider_id"])
                session.add(row)
            row.policy, row.granted_at, row.revoked_at = body.policy, utc_now().isoformat(), None
            row.attestation = self.db.evidence_signer.sign("chat_provider_consent", self.evidence(row))
            advance_head(session, "chat_consent", ctx, ctx.actor.actor_id + ":" + provider["provider_id"], previous, self.head(row))
            self.chat.core.audit_logger.record("chat.provider.consent.granted", ctx, row.id, AuditStatus.ALLOWED,
                {"provider_id": provider["provider_id"], "policy": body.policy}, session=session)
        return await self.policies(ctx)

    def revoke(self, ctx, provider_id):
        from modules.core.conversations import ChatError
        self.chat.authorize(ctx)
        with self.db.session(write=True) as session:
            self.chat.authorize(ctx, session=session)
            row = session.query(ProviderConsentModel).filter_by(**self.chat.scope(ctx), provider_id=provider_id).with_for_update().first()
            if not row:
                raise ChatError("consent_not_found", 404)
            self.verify(session, ctx, provider_id, row)
            previous = self.head(row)
            row.revoked_at = utc_now().isoformat()
            row.attestation = self.db.evidence_signer.sign("chat_provider_consent", self.evidence(row))
            advance_head(session, "chat_consent", ctx, ctx.actor.actor_id + ":" + provider_id, previous, self.head(row))
            self.chat.core.audit_logger.record("chat.provider.consent.revoked", ctx, row.id, AuditStatus.ALLOWED,
                {"provider_id": provider_id}, session=session)
        return dict(revoked=True)

    def preferences(self, ctx, body=None):
        self.chat.authorize(ctx)
        with self.db.session(write=body is not None) as session:
            self.chat.authorize(ctx, session=session)
            # Language belongs to the authenticated person in this organization, not a project.
            from database.schema import OrganizationModel
            if body:
                session.query(OrganizationModel).filter_by(id=ctx.organization_id).with_for_update().one()
            row = session.query(StudioPreferenceModel).filter_by(organization_id=ctx.organization_id, actor_id=ctx.actor.actor_id).first()
            if body:
                if not row:
                    row = StudioPreferenceModel(organization_id=ctx.organization_id, actor_id=ctx.actor.actor_id)
                    session.add(row)
                row.locale = body.locale
            return dict(organization_id=ctx.organization_id, actor_id=ctx.actor.actor_id, locale=row.locale if row else "id-ID")
