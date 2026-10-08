"""Core revalidation of a server session inside the existing authorization transaction."""
from datetime import datetime, timezone

from database.schema import AuthSessionModel, ExternalIdentityModel


def session_identity(session, token_hash):
    query = session.query(AuthSessionModel).filter_by(token_hash=token_hash).populate_existing()
    if session.info.get("write"):
        query = query.with_for_update()
    record = query.first()
    if record is None or record.revoked_at is not None:
        return None
    expiry = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    if expiry <= datetime.now(timezone.utc):
        return None
    query = session.query(ExternalIdentityModel).filter_by(id=record.identity_id).populate_existing()
    if session.info.get("write"):
        query = query.with_for_update()
    identity = query.first()
    if identity is None or identity.status != "active":
        return None
    # Production login cannot elevate or reuse the shared Local development cohort.
    if identity.actor_id == "studio_local_owner" or identity.organization_id == "org_studio_local":
        return None
    return identity
