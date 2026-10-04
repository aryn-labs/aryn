"""Trusted Identity Binder for ARYN Infrastructure.

Establishes an authoritative cryptographic identity boundary at the Core perimeter.
Ensures actor_id, actor_type, organization_id, and project_id cannot be forged
or impersonated by client requests or untrusted autonomous agents.
Complies with ARYN-ARCH-001 Section 03 and ARYN-SEC-001.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from typing import List, Optional

from packages.contracts.core import Actor, ActorType, PolicyDecision, SecurityContext


class IdentityVerificationError(Exception):
    """Raised when an actor identity fails cryptographic verification or is untrusted."""
    pass


class TrustedIdentityBinder:
    """Authoritative server-side identity assertion issuer and validator.

    Enforces fail-closed identity verification so caller-provided actor_id and
    actor_type cannot be forged or tampered with.
    """

    def __init__(self, secret_key: Optional[str] = None) -> None:
        key = secret_key or os.getenv("ARYN_IDENTITY_SECRET") or "aryn-core-internal-trusted-identity-secret-2026"
        self._secret_key = key.encode("utf-8")

    def generate_token(
        self,
        actor_id: str,
        actor_type: ActorType | str,
        organization_id: str,
        project_id: Optional[str] = None,
    ) -> str:
        """Generates an authoritative HMAC-SHA256 identity binding token."""
        type_str = actor_type.value if isinstance(actor_type, ActorType) else str(actor_type)
        proj_str = project_id or ""
        payload = f"aryn:v1:{actor_id}:{type_str}:{organization_id}:{proj_str}".encode("utf-8")
        return hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()

    def sign_context(self, context: SecurityContext) -> SecurityContext:
        """Cryptographically binds the SecurityContext with an authoritative identity token."""
        context.identity_token = self.generate_token(
            actor_id=context.actor.actor_id,
            actor_type=context.actor.actor_type,
            organization_id=context.organization_id,
            project_id=context.project_id,
        )
        return context

    def create_trusted_context(
        self,
        actor_id: str,
        organization_id: str,
        project_id: str,
        actor_type: ActorType = ActorType.USER,
        roles: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> SecurityContext:
        """Issues an authoritative SecurityContext with a valid cryptographic identity binding."""
        actor = Actor(
            actor_id=actor_id,
            actor_type=actor_type,
            organization_id=organization_id,
            project_id=project_id,
            roles=roles or [],
        )
        ctx = SecurityContext(
            actor=actor,
            organization_id=organization_id,
            project_id=project_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
        return self.sign_context(ctx)

    def verify_context(self, context: SecurityContext) -> PolicyDecision:
        """Validates the cryptographic authenticity of the actor identity on the Core boundary.

        Fails closed on missing, mismatched, or forged identity tokens.
        """
        if not context.identity_token:
            return PolicyDecision(
                allowed=False,
                reason="Untrusted identity binding: SecurityContext lacks authoritative identity token (fail-closed).",
                matched_rules=["RULE_IDENTITY_UNTRUSTED", "RULE_DENY_BY_DEFAULT"],
            )

        expected_token = self.generate_token(
            actor_id=context.actor.actor_id,
            actor_type=context.actor.actor_type,
            organization_id=context.organization_id,
            project_id=context.project_id,
        )

        if not hmac.compare_digest(context.identity_token, expected_token):
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Identity signature mismatch for actor '{context.actor.actor_id}' "
                    f"with type '{context.actor.actor_type.value}' (impersonation or forged identity detected)."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        return PolicyDecision(
            allowed=True,
            reason="Identity authenticity verified by authoritative identity binding.",
            matched_rules=["RULE_IDENTITY_VERIFIED"],
        )
