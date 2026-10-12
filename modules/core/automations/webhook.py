"""TLS scoped bearer ingress: fixed reviewed input, durable dedup, existing Core dispatch."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from sqlalchemy import func
from fastapi import HTTPException
from database.schema import (
    AutomationDefinitionModel as Definition,
    AutomationEventModel as Event,
    AutomationOccurrenceModel as Occurrence,
)
from modules.core.automations.service import BUSY, READY
from modules.core.automations.recurrence import instant
from modules.core.workflows.executor import digest
from packages.contracts.automation import AutomationEvent


class WebhookIngress:
    def __init__(self, scheduler):
        self.scheduler = scheduler

    def credential(self, ctx, identifier, body):
        s = self.scheduler
        with s.db.session(write=True) as session:
            s.manage(session, ctx)
            row, definition = s.get(session, Definition, ctx, identifier, True)
            s.approval(session, ctx, definition)
            if (
                definition["revision"] != body.expected_revision
                or definition["configuration"]["schedule"]["kind"] != "webhook"
            ):
                raise HTTPException(409, "Webhook configuration changed.")
            token = secrets.token_urlsafe(32) if body.action == "rotate" else None
            _, event = s.add(
                session,
                ctx,
                Event,
                AutomationEvent,
                "automation_event",
                automation_id=identifier,
                event="webhook.credential." + body.action,
                actor_id=ctx.actor.actor_id,
            )
            definition["webhook_credential"] = (
                dict(
                    id=event["id"],
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    payload_hash=definition["payload_hash"],
                )
                if token
                else None
            )
            s.put(session, ctx, row, definition)
            s.audit(
                session,
                ctx,
                "core.automation.webhook." + body.action,
                identifier,
                credential_id=event["id"],
            )
            return {
                "id": event["id"],
                "secret": token,
                "authentication": "scoped_bearer_over_tls",
                "one_time": True,
            }

    def accept(self, identifier, token, timestamp, signal):
        s = self.scheduler
        # Resolve an indexed, immutable issuance event; no unbounded definition scan.
        with s.db.session() as session:
            hint = session.get(Event, identifier)
            if not hint:
                raise HTTPException(401, "Webhook authentication failed.")
            parent = session.get(Definition, hint.automation_id)
            if not parent:
                raise HTTPException(401, "Webhook authentication failed.")
            system = s.permissions.identity_binder.create_trusted_context(
                "core_webhook_lookup", parent.organization_id, parent.project_id
            )
            _, definition = s._verified(session, Definition, system, parent.id)
        ctx = s.owner_context(definition)
        credential = definition.get("webhook_credential") or {}
        if credential.get("id") != identifier or not hmac.compare_digest(
            credential.get("token_hash", ""), hashlib.sha256(token.encode()).hexdigest()
        ):
            raise HTTPException(401, "Webhook authentication failed.")
        from packages.contracts.automation import AutomationInput

        s.preflight_target(
            ctx, AutomationInput.model_validate(definition["configuration"]).target
        )
        with s.db.session(write=True) as session:
            s.manage(session, ctx)
            row, definition = s.get(session, Definition, ctx, definition["id"], True)
            _, issued = s.get(session, Event, ctx, identifier)
            credential = definition.get("webhook_credential") or {}
            if (
                credential.get("id") != identifier
                or issued["event"] != "webhook.credential.rotate"
                or not hmac.compare_digest(
                    credential.get("token_hash", ""),
                    hashlib.sha256(token.encode()).hexdigest(),
                )
                or credential.get("payload_hash") != definition["payload_hash"]
            ):
                raise HTTPException(401, "Webhook authentication failed.")
            try:
                age = abs((instant(s.clock()) - instant(timestamp)).total_seconds())
            except (ValueError, TypeError):
                raise HTTPException(401, "Webhook timestamp invalid.") from None
            if age > 300:
                raise HTTPException(401, "Webhook timestamp expired.")
            s.approval(session, ctx, definition)
            if (
                definition["status"] != "enabled"
                or definition["configuration"]["schedule"]["kind"] != "webhook"
            ):
                raise HTTPException(409, "Webhook is paused or unavailable.")
            key, event_digest = (
                "webhook:" + hashlib.sha256(signal.event_id.encode()).hexdigest(),
                digest(signal.model_dump(mode="json")),
            )
            old = (
                session.query(Occurrence)
                .filter_by(automation_id=definition["id"], occurrence_key=key)
                .first()
            )
            if old:
                _, occurrence = s.get(session, Occurrence, ctx, old.id)
                if occurrence.get("trigger_event_digest") != event_digest:
                    raise HTTPException(409, "Event identity conflicts.")
                return occurrence, False
            recent = (
                session.query(func.count(Occurrence.id))
                .filter(
                    Occurrence.automation_id == definition["id"],
                    Occurrence.occurrence_key.like("webhook:%"),
                    Occurrence.created_at >= instant(s.clock()) - timedelta(minutes=1),
                )
                .scalar()
            )
            if recent >= 12:
                raise HTTPException(429, "Webhook rate limit exceeded.")
            busy = (
                session.query(Occurrence.id)
                .filter(
                    Occurrence.automation_id == definition["id"],
                    Occurrence.status.in_(BUSY),
                )
                .first()
            )
            ready = (
                session.query(func.count(Occurrence.id))
                .filter(
                    Occurrence.automation_id == definition["id"],
                    Occurrence.status.in_(READY),
                )
                .scalar()
            )
            status, error = "queued", None
            if busy and definition["configuration"]["policy"]["overlap"] == "skip":
                status, error = "skipped", "overlap"
            elif ready >= 3:
                status, error = "skipped", "overlap_queue_full"
            occurrence, fresh = s.occurrence(
                session, ctx, definition, key, s.clock(), status, error
            )
            occurrence["trigger_event_digest"] = event_digest
            stored, _ = s.get(session, Occurrence, ctx, occurrence["id"], True)
            s.put(session, ctx, stored, occurrence)
            s.event(
                session,
                ctx,
                definition,
                "webhook.accepted",
                occurrence,
                credential_id=identifier,
                event_digest=event_digest,
            )
            s.manage(session, ctx)
            return occurrence, fresh
