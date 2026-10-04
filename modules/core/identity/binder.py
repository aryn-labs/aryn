"""Trusted Identity Binder for ARYN Infrastructure.

CRITICAL SECURITY ARCHITECTURE NOTICE:
This module establishes an internal, authoritative cryptographic identity boundary
at the ARYN Core perimeter. It is strictly an INTERNAL Core component.

Without trusted upstream authentication (such as an external API Gateway with
OIDC / OAuth2 / mTLS), this identity binding mechanism is INTERNAL-ONLY.
Direct exposure of identity issuance or raw SecurityContext ingestion from
untrusted networks is strictly prohibited. External clients must never be permitted
to assert or self-sign their own SecurityContext.

Complies with ARYN-ARCH-001 Section 03 and ARYN-SEC-001.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from packages.contracts.core import Actor, ActorType, PolicyDecision, SecurityContext


class IdentityVerificationError(Exception):
    """Raised when an actor identity fails cryptographic verification or is untrusted."""
    pass


def _b64_encode(data: bytes) -> str:
    """URL-safe base64 encoding without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    """URL-safe base64 decoding with padding restoration."""
    rem = len(data) % 4
    if rem > 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("ascii"))


class TrustedIdentityBinder:
    """Authoritative internal identity assertion issuer and validator.

    Enforces fail-closed identity verification so caller-provided actor_id and
    actor_type cannot be forged or tampered with.

    Key principles:
    1. Zero fallback secret: An explicit, non-empty secret key is required.
    2. Strict validation: Binds actor_id, actor_type, organization_id, project_id,
       issued_at (iat), and expiry (exp).
    3. Key rotation: Supports primary signing key plus active secondary verification keys.
    4. Internal-only issuance: Clients cannot self-sign.
    """

    TOKEN_PREFIX = "arynbind_v2"

    def __init__(
        self,
        secret_key: Optional[Union[str, bytes]] = None,
        key_id: str = "k1",
        secondary_keys: Optional[Union[Dict[str, Union[str, bytes]], List[Union[str, bytes]]]] = None,
        default_ttl_seconds: int = 3600,
    ) -> None:
        """Initializes the trusted identity binder with an explicit secret.

        Raises:
            ValueError: If secret_key is not provided and ARYN_IDENTITY_SECRET is unset/empty,
                        or if the provided key is empty/whitespace.
        """
        raw_key = secret_key if secret_key is not None else os.getenv("ARYN_IDENTITY_SECRET")
        if raw_key is None:
            raise ValueError(
                "TrustedIdentityBinder requires an explicit non-empty secret_key (or ARYN_IDENTITY_SECRET "
                "environment variable). Fallback default secrets are strictly prohibited."
            )

        if isinstance(raw_key, str):
            key_bytes = raw_key.strip().encode("utf-8")
        elif isinstance(raw_key, bytes):
            key_bytes = raw_key.strip()
        else:
            raise TypeError("secret_key must be str or bytes")

        if not key_bytes:
            raise ValueError("Secret key cannot be empty or whitespace. Explicit entropy is required.")

        self._primary_key_id = key_id.strip() if key_id else "k1"
        self._primary_key = key_bytes
        self._default_ttl_seconds = default_ttl_seconds

        # Verification keys map: key_id -> bytes
        self._verification_keys: Dict[str, bytes] = {self._primary_key_id: self._primary_key}
        if secondary_keys:
            if isinstance(secondary_keys, dict):
                for kid, k in secondary_keys.items():
                    kb = k.strip().encode("utf-8") if isinstance(k, str) else k.strip()
                    if kb:
                        self._verification_keys[kid.strip()] = kb
            elif isinstance(secondary_keys, list):
                for idx, k in enumerate(secondary_keys):
                    kb = k.strip().encode("utf-8") if isinstance(k, str) else k.strip()
                    if kb:
                        self._verification_keys[f"rot_{idx+1}"] = kb

    def issue_token(
        self,
        actor_id: str,
        actor_type: Union[ActorType, str],
        organization_id: str,
        project_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        custom_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Issues an authoritative cryptographically bound identity token."""
        if not actor_id or not str(actor_id).strip():
            raise ValueError("actor_id cannot be empty")
        if not organization_id or not str(organization_id).strip():
            raise ValueError("organization_id cannot be empty")

        type_str = actor_type.value if isinstance(actor_type, ActorType) else str(actor_type).strip()
        proj_str = str(project_id).strip() if project_id else ""

        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        exp = now + ttl

        header = {
            "alg": "HS256",
            "typ": "ARYN-ID",
            "kid": self._primary_key_id,
        }
        claims = {
            "sub": str(actor_id).strip(),
            "typ": type_str,
            "org": str(organization_id).strip(),
            "prj": proj_str,
            "iat": round(now, 2),
            "exp": round(exp, 2),
            "jti": str(uuid.uuid4()),
        }
        if custom_claims:
            claims.update(custom_claims)

        header_b64 = _b64_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        claims_b64 = _b64_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = f"{header_b64}.{claims_b64}".encode("ascii")

        sig = hmac.new(self._primary_key, signing_input, hashlib.sha256).digest()
        sig_b64 = _b64_encode(sig)

        return f"{self.TOKEN_PREFIX}.{header_b64}.{claims_b64}.{sig_b64}"

    def bind_context(
        self,
        context: SecurityContext,
        ttl_seconds: Optional[int] = None,
    ) -> SecurityContext:
        """Internal helper: binds an authoritative identity token onto a SecurityContext."""
        context.identity_token = self.issue_token(
            actor_id=context.actor.actor_id,
            actor_type=context.actor.actor_type,
            organization_id=context.organization_id,
            project_id=context.project_id,
            ttl_seconds=ttl_seconds,
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
        ttl_seconds: Optional[int] = None,
    ) -> SecurityContext:
        """Issues an authoritative SecurityContext with a valid cryptographic identity token."""
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
        return self.bind_context(ctx, ttl_seconds=ttl_seconds)

    def verify_context(self, context: SecurityContext) -> PolicyDecision:
        """Validates the cryptographic authenticity and claims of the identity token.

        Fails closed on missing, malformed, expired, mismatched, or forged identity tokens.
        """
        token = context.identity_token
        if not token or not isinstance(token, str) or not token.strip():
            return PolicyDecision(
                allowed=False,
                reason="Untrusted identity binding: SecurityContext lacks authoritative identity token (fail-closed).",
                matched_rules=["RULE_IDENTITY_UNTRUSTED", "RULE_DENY_BY_DEFAULT"],
            )

        token = token.strip()
        parts = token.split(".")
        if len(parts) != 4 or parts[0] != self.TOKEN_PREFIX:
            return PolicyDecision(
                allowed=False,
                reason="Untrusted identity binding: Malformed identity token structure.",
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        _, header_b64, claims_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{claims_b64}".encode("ascii")

        try:
            header = json.loads(_b64_decode(header_b64).decode("utf-8"))
            claims = json.loads(_b64_decode(claims_b64).decode("utf-8"))
            provided_sig = _b64_decode(sig_b64)
        except Exception:
            return PolicyDecision(
                allowed=False,
                reason="Untrusted identity binding: Unable to decode token payload or signature.",
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        # 1. Resolve verification key(s)
        kid = header.get("kid")
        possible_keys: List[bytes] = []
        if kid and kid in self._verification_keys:
            possible_keys.append(self._verification_keys[kid])
        else:
            # Fallback across all active keys (primary + rotation)
            possible_keys = list(self._verification_keys.values())

        # 2. Cryptographic signature check (constant-time)
        valid_sig = False
        for k in possible_keys:
            expected_sig = hmac.new(k, signing_input, hashlib.sha256).digest()
            if hmac.compare_digest(provided_sig, expected_sig):
                valid_sig = True
                break

        if not valid_sig:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Identity signature mismatch for actor '{context.actor.actor_id}' "
                    f"(impersonation or forged identity detected)."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        # 3. Expiration and timestamp validation
        now = time.time()
        exp = claims.get("exp")
        iat = claims.get("iat")

        if exp is None or not isinstance(exp, (int, float)):
            return PolicyDecision(
                allowed=False,
                reason="Untrusted identity binding: Missing or invalid expiry claim in token.",
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        if now > exp:
            return PolicyDecision(
                allowed=False,
                reason=f"Untrusted identity binding: Token expired at {exp} (current time {now}).",
                matched_rules=["RULE_IDENTITY_EXPIRED", "RULE_DENY_BY_DEFAULT"],
            )

        if iat is not None and isinstance(iat, (int, float)):
            # Disallow tokens from the future (with 30-second clock skew tolerance)
            if iat > now + 30:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Untrusted identity binding: Token issued in the future (iat: {iat}, current: {now}).",
                    matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
                )

        # 4. Strict claims-to-context binding verification
        actor_id_claim = claims.get("sub")
        if actor_id_claim != context.actor.actor_id:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Token subject '{actor_id_claim}' does not match "
                    f"context actor_id '{context.actor.actor_id}'."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        actor_type_claim = claims.get("typ")
        ctx_actor_type = (
            context.actor.actor_type.value
            if isinstance(context.actor.actor_type, ActorType)
            else str(context.actor.actor_type)
        )
        if actor_type_claim != ctx_actor_type:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Token actor_type '{actor_type_claim}' does not match "
                    f"context actor_type '{ctx_actor_type}'."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        org_claim = claims.get("org")
        if org_claim != context.organization_id:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Token org '{org_claim}' does not match context org "
                    f"'{context.organization_id}'."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        if org_claim != context.actor.organization_id:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Token org '{org_claim}' does not match actor organization "
                    f"'{context.actor.organization_id}'."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        prj_claim = claims.get("prj") or None
        ctx_prj = context.project_id or None
        if prj_claim != ctx_prj:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Untrusted identity binding: Token project '{prj_claim}' does not match context project "
                    f"'{ctx_prj}'."
                ),
                matched_rules=["RULE_IDENTITY_TAMPERED", "RULE_DENY_BY_DEFAULT"],
            )

        return PolicyDecision(
            allowed=True,
            reason="Identity authenticity and claims verified by authoritative identity binding.",
            matched_rules=["RULE_IDENTITY_VERIFIED"],
        )
