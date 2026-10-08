"""OIDC authentication boundary. Core membership remains the only role authority."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import os
import secrets
import time
from urllib.parse import urlsplit

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from database.schema import AuthSessionModel, ExternalIdentityModel, LoginTransactionModel, MembershipModel
from modules.core.identity.sessions import session_identity

HOSTED_COOKIE = "__Host-aryn_session"
LOGIN_COOKIE = "__Host-aryn_login"
principal_context = ContextVar("studio_authenticated_principal", default=None)


def https_url(value, *, origin=False):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or "\\" in value
            or (origin and parsed.path not in {"", "/"})):
        raise ValueError("Hosted authentication requires explicit HTTPS URLs.")
    _ = parsed.port
    return value.rstrip("/") if origin else value


class AuthenticationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    mode: str = "disabled"
    environment: str = "development"
    public_origin: str = ""
    issuer: str = ""
    client_id: str = ""
    client_secret: SecretStr = Field(default_factory=lambda: SecretStr(""))
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""
    redirect_uri: str = ""
    session_secret: SecretStr = Field(default_factory=lambda: SecretStr(""))
    identity_secret: SecretStr = Field(default_factory=lambda: SecretStr(""))
    trusted_proxies: tuple[str, ...] = ()
    session_ttl: int = Field(default=3600, ge=60, le=28800)

    @model_validator(mode="after")
    def validate_boundary(self):
        if self.mode == "local-development" and self.environment == "development":
            return self
        if self.mode != "oidc":
            raise ValueError("Explicit local-development authentication or configured OIDC is required.")
        for name in ("public_origin", "issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "redirect_uri"):
            https_url(getattr(self, name), origin=name == "public_origin")
        if self.public_origin.endswith("/") or self.redirect_uri != self.public_origin + "/auth/callback":
            raise ValueError("Redirect URI must exactly match the configured public callback.")
        if not self.client_id or len(self.client_id) > 255:
            raise ValueError("OIDC client ID is required.")
        secrets_used = (self.session_secret.get_secret_value(), self.identity_secret.get_secret_value())
        if any(len(value) < 32 for value in secrets_used) or secrets_used[0] == secrets_used[1]:
            raise ValueError("Distinct explicit session and Core identity secrets of at least 32 characters are required.")
        for proxy in self.trusted_proxies:
            ipaddress.ip_address(proxy)  # Exact addresses; no wildcard or whole-network trust.
        return self

    @classmethod
    def from_env(cls, settings):
        return cls(mode=os.getenv("ARYN_AUTH_MODE", "disabled"), environment=settings.aryn_env,
            public_origin=os.getenv("ARYN_PUBLIC_ORIGIN", ""), issuer=os.getenv("ARYN_OIDC_ISSUER", ""),
            client_id=os.getenv("ARYN_OIDC_CLIENT_ID", ""), client_secret=SecretStr(os.getenv("ARYN_OIDC_CLIENT_SECRET", "")),
            authorization_endpoint=os.getenv("ARYN_OIDC_AUTHORIZATION_ENDPOINT", ""),
            token_endpoint=os.getenv("ARYN_OIDC_TOKEN_ENDPOINT", ""), jwks_uri=os.getenv("ARYN_OIDC_JWKS_URI", ""),
            redirect_uri=os.getenv("ARYN_OIDC_REDIRECT_URI", ""), session_secret=SecretStr(os.getenv("ARYN_SESSION_SECRET", "")),
            identity_secret=SecretStr(os.getenv("ARYN_IDENTITY_SECRET", "")),
            trusted_proxies=tuple(x.strip() for x in os.getenv("ARYN_TRUSTED_PROXIES", "").split(",") if x.strip()),
            session_ttl=int(os.getenv("ARYN_SESSION_TTL", "3600")))

    def check_request(self, request):
        expected = urlsplit(self.public_origin)
        if request.headers.get("host") != expected.netloc:
            raise HTTPException(403)
        # Never consume identity headers, even when a trusted network proxy sent them.
        if any(request.headers.get(name) is not None for name in ("x-user", "x-role", "x-forwarded-user", "x-auth-request-user")):
            raise HTTPException(403)
        if request.headers.get("forwarded") is not None:
            raise HTTPException(403)  # Supported proxy contract is deliberately narrow.
        forwarded = [name for name in request.headers if name.startswith("x-forwarded-")]
        if forwarded:
            if request.client is None or request.client.host not in self.trusted_proxies:
                raise HTTPException(403)
            if request.headers.get("x-forwarded-proto") != "https":
                raise HTTPException(403)
            if request.headers.get("x-forwarded-host", expected.netloc) != expected.netloc:
                raise HTTPException(403)
            if any(name not in {"x-forwarded-proto", "x-forwarded-host", "x-forwarded-for"} for name in forwarded):
                raise HTTPException(403)
        elif request.url.scheme != "https":
            raise HTTPException(403)
        if request.headers.get("origin") not in {None, self.public_origin}:
            raise HTTPException(403)


class OIDCProvider:
    """Pinned provider endpoints, Authlib code/PKCE exchange and PyJWT verification."""
    def __init__(self, config, transport=None):
        self.config = config
        self.transport = transport
        self._keys = None
        self._keys_until = 0
        self._key_lock = asyncio.Lock()

    def client(self, state=None):
        return AsyncOAuth2Client(self.config.client_id, self.config.client_secret.get_secret_value() or None,
            token_endpoint_auth_method="client_secret_basic" if self.config.client_secret.get_secret_value() else "none",
            redirect_uri=self.config.redirect_uri, scope="openid", state=state, code_challenge_method="S256",
            transport=self.transport, trust_env=False, follow_redirects=False, timeout=10)

    async def authorization_url(self, state, nonce, verifier):
        async with self.client() as client:
            url, _ = client.create_authorization_url(self.config.authorization_endpoint,
                state=state, nonce=nonce, code_verifier=verifier, response_mode="query")
            return url

    async def keys(self, refresh=False):
        async with self._key_lock:
            if refresh or self._keys is None or time.monotonic() >= self._keys_until:
                async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=10) as client:
                    response = await client.get(self.config.jwks_uri)
                    response.raise_for_status()
                    data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("keys"), list) or len(data["keys"]) > 32:
                    raise ValueError("Invalid provider keys.")
                self._keys, self._keys_until = data["keys"], time.monotonic() + 300
            return self._keys

    async def verify(self, encoded, nonce):
        if not isinstance(encoded, str) or len(encoded) > 16384:
            raise ValueError("Invalid ID token.")
        header = jwt.get_unverified_header(encoded)
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in {"RS256", "ES256"} or not isinstance(kid, str) or header.get("crit"):
            raise ValueError("Unsupported token key.")
        key = None
        for refresh in (False, True):
            candidates = [item for item in await self.keys(refresh) if item.get("kid") == kid
                          and item.get("use", "sig") == "sig" and item.get("alg", alg) == alg]
            if len(candidates) == 1:
                key = jwt.PyJWK(candidates[0], algorithm=alg).key
                break
        if key is None:
            raise ValueError("Unknown provider key.")
        claims = jwt.decode(encoded, key, algorithms=[alg], issuer=self.config.issuer,
            audience=self.config.client_id, options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]})
        if not isinstance(claims["sub"], str) or not claims["sub"] or len(claims["sub"]) > 255:
            raise ValueError("Invalid subject.")
        if not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"].encode(), nonce.encode()):
            raise ValueError("Invalid nonce.")
        if (isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != self.config.client_id
                or claims.get("azp", self.config.client_id) != self.config.client_id):
            raise ValueError("Invalid authorized party.")
        return claims

    async def exchange(self, callback_url, state, verifier, nonce):
        async with self.client(state=state) as client:
            token = await client.fetch_token(self.config.token_endpoint, authorization_response=callback_url,
                code_verifier=verifier)
        return await self.verify(token.get("id_token"), nonce)


@dataclass(frozen=True)
class Principal:
    actor_id: str
    organization_id: str
    session_id: str | None = None


class HostedAuthentication:
    def __init__(self, db, config, provider=None):
        self.db, self.config = db, config
        self.provider = provider or OIDCProvider(config)
        self.secret = config.session_secret.get_secret_value().encode()

    def digest(self, kind, value):
        return hmac.new(self.secret, (kind + ":" + value).encode(), hashlib.sha256).hexdigest()

    def csrf(self, sid):
        return self.digest("csrf", sid)

    def principal(self, request):
        sid = request.cookies.get(HOSTED_COOKIE, "")
        if not sid or len(sid) > 128:
            raise HTTPException(401)
        token_hash = self.digest("session", sid)
        with self.db.session() as session:
            identity = session_identity(session, token_hash)
            if identity is None:
                raise HTTPException(401)
            return Principal(identity.actor_id, identity.organization_id, token_hash)

    def mount(self, app):
        @app.get("/auth/login")
        async def login(request: Request):
            # No user-controlled redirect/scope/role/issuer parameters.
            if request.query_params:
                raise HTTPException(400)
            state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
            with self.db.session(write=True) as session:
                session.query(LoginTransactionModel).filter(LoginTransactionModel.expires_at < datetime.now(timezone.utc)).delete()
                if session.query(LoginTransactionModel).count() >= 256:
                    raise HTTPException(429)
                session.add(LoginTransactionModel(state_hash=self.digest("state", state), browser_hash=self.digest("browser", browser),
                    nonce=nonce, code_verifier=verifier, expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
            response = RedirectResponse(await self.provider.authorization_url(state, nonce, verifier), status_code=303)
            response.set_cookie(LOGIN_COOKIE, browser, secure=True, httponly=True, samesite="lax", max_age=300, path="/")
            return response

        @app.get("/auth/callback")
        async def callback(request: Request):
            try:
                if (set(request.query_params) != {"state", "code"} or any(len(request.query_params.getlist(k)) != 1 for k in ("state", "code"))
                        or any(not request.query_params[k] or len(request.query_params[k]) > 2048 for k in ("state", "code"))):
                    raise ValueError("Invalid callback.")
                state, browser = request.query_params["state"], request.cookies.get(LOGIN_COOKIE, "")
                with self.db.session(write=True) as session:
                    transaction = session.query(LoginTransactionModel).filter_by(state_hash=self.digest("state", state)).with_for_update().first()
                    if transaction is None or not secrets.compare_digest(transaction.browser_hash, self.digest("browser", browser)):
                        raise ValueError("Invalid login transaction.")
                    expiry = transaction.expires_at.replace(tzinfo=timezone.utc) if transaction.expires_at.tzinfo is None else transaction.expires_at
                    if expiry <= datetime.now(timezone.utc):
                        raise ValueError("Expired login transaction.")
                    nonce, verifier = transaction.nonce, transaction.code_verifier
                    session.delete(transaction)  # Consume before external await; no replay on exchange failure.
                claims = await self.provider.exchange(self.config.redirect_uri + "?" + request.url.query, state, verifier, nonce)
                sid = secrets.token_urlsafe(32)  # Never reuse the browser's pre-login session identifier.
                with self.db.session(write=True) as session:
                    # Match Core lock order: existing session, identity, membership.
                    old_hash = self.digest("session", request.cookies.get(HOSTED_COOKIE, ""))
                    session.query(AuthSessionModel).filter_by(token_hash=old_hash).update({"revoked_at": datetime.now(timezone.utc)})
                    identity = session.query(ExternalIdentityModel).filter_by(issuer=claims["iss"], subject=claims["sub"], status="active").with_for_update().first()
                    if (identity is None or identity.actor_id == "studio_local_owner" or identity.organization_id == "org_studio_local"):
                        raise ValueError("Unprovisioned identity.")
                    member = session.query(MembershipModel).filter_by(organization_id=identity.organization_id, user_id=identity.actor_id,
                        status="active").with_for_update().first()
                    if member is None:
                        raise ValueError("Membership required.")
                    session.add(AuthSessionModel(token_hash=self.digest("session", sid), identity_id=identity.id,
                        expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.config.session_ttl)))
                response = RedirectResponse(self.config.public_origin + "/", status_code=303)
                response.set_cookie(HOSTED_COOKIE, sid, secure=True, httponly=True, samesite="lax", path="/", max_age=self.config.session_ttl)
                response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
                return response
            except Exception:
                # No code, provider response, token or exception details in public errors/logs.
                raise HTTPException(401) from None

        @app.post("/api/logout")
        async def logout(request: Request):
            principal = self.principal(request)
            with self.db.session(write=True) as session:
                session.query(AuthSessionModel).filter_by(token_hash=principal.session_id).update({"revoked_at": datetime.now(timezone.utc)})
            response = JSONResponse({"logged_out": True})
            response.delete_cookie(HOSTED_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
            return response
