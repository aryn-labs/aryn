"""Signed offline OIDC provider, real Studio/Core/database; no production credentials."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time
from urllib.parse import parse_qs

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

from database.connection import DatabaseManager, create_db_engine, init_db
from database.repositories.organization_repo import OrganizationRepository
from database.schema import AuthSessionModel, ExternalIdentityModel, MembershipModel, OrganizationModel, ProjectModel
from modules.core.permissions.engine import PermissionDeniedError
from packages.config import get_settings
from services.api.authentication import AuthenticationSettings, HOSTED_COOKIE, OIDCProvider
from services.api.studio import create_app, DEV_ACTOR, DEV_ORG
from tests.studio_runtime import IsolatedTestRuntime

ORIGIN = "https://studio.example"
ISSUER = "https://identity.example"


@pytest.fixture
def hosted(tmp_path, monkeypatch, request):
    for name, value in {"ARYN_ENV": "production", "ARYN_AUTH_MODE": "oidc", "ARYN_STUDIO_HOST": "127.0.0.1",
                        "ARYN_STUDIO_PORT": "8710", "ARYN_RUNTIME_BASE_URL": "http://127.0.0.1:8642",
                        "ARYN_9ROUTER_BASE_URL": "http://127.0.0.1:20128/v1"}.items():
        monkeypatch.setenv(name, value)
    config = AuthenticationSettings(mode="oidc", environment="production", public_origin=ORIGIN, issuer=ISSUER,
        client_id="aryn", authorization_endpoint=ISSUER + "/authorize", token_endpoint=ISSUER + "/token",
        jwks_uri=ISSUER + "/jwks", redirect_uri=ORIGIN + "/auth/callback",
        session_secret="session-synthetic-credential-32-bytes-secure", identity_secret="identity-synthetic-credential-32-bytes-secure",
        trusted_proxies=("127.0.0.1",))
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    control = {"nonce": "", "claims": {}, "key": private, "kid": "one", "state": "", "verifier": None}
    calls = []

    def provider_response(request):
        calls.append(request.url.path)
        if request.url.path == "/jwks":
            key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(control["key"].public_key()))
            key.update(kid=control["kid"], use="sig", alg="RS256")
            return httpx.Response(200, json={"keys": [key]})
        assert request.url.path == "/token"
        data = parse_qs(request.content.decode())
        verifier = data["code_verifier"][0]
        control["verifier"] = verifier
        from authlib.common.encoding import urlsafe_b64encode
        assert urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode() == control["challenge"]
        assert data["redirect_uri"] == [config.redirect_uri]
        assert data["grant_type"] == ["authorization_code"]
        claims = {"iss": ISSUER, "sub": "subject-1", "aud": "aryn", "iat": int(time.time()),
                  "exp": int(time.time()) + 300, "nonce": control["nonce"],
                  "email": "admin@example", "roles": ["admin"], "actor_type": "system"}
        claims.update(control["claims"])
        token = jwt.encode(claims, control.get("signing_key", control["key"]), algorithm="RS256", headers={"kid": control["kid"]})
        return httpx.Response(200, json={"access_token": "synthetic-private-access-token", "token_type": "Bearer", "id_token": token})

    if getattr(request, "param", None) == "postgresql":
        db = request.getfixturevalue("postgres_db").db
    else:
        db = DatabaseManager(create_db_engine(f"sqlite:///{(tmp_path / 'hosted.sqlite3').as_posix()}"))
        init_db(db.engine)
    with db.session(write=True) as session:
        repo = OrganizationRepository(session)
        repo.create_organization("org", "Hosted", "hosted")
        repo.add_member("org", "human", role="operator")
        session.add_all([ProjectModel(id="project", organization_id="org", name="Project", slug="project"),
                         ProjectModel(id="private", organization_id="org", name="Private", slug="private")])
        session.flush()
        repo.add_project_member("project", "human", "operator")
        repo.create_organization("foreign", "Foreign", "foreign")
        session.add(ProjectModel(id="foreign-project", organization_id="foreign", name="Foreign", slug="foreign"))
        session.add(ExternalIdentityModel(id="external", issuer=ISSUER, subject="subject-1", actor_id="human", organization_id="org", status="active"))
    runtime = IsolatedTestRuntime()
    provider = OIDCProvider(config, httpx.MockTransport(provider_response))
    app = create_app(db, runtime, authentication=config, identity_provider=provider)
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 5555)) as client:
        yield client, app, db, config, control, calls
    db.engine.dispose()


def start_login(hosted):
    client, _, _, _, control, _ = hosted
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 303
    query = parse_qs(httpx.URL(response.headers["location"]).query.decode())
    assert query["code_challenge_method"] == ["S256"]
    assert query["response_type"] == ["code"] and query["scope"] == ["openid"]
    control.update(nonce=query["nonce"][0], state=query["state"][0], challenge=query["code_challenge"][0])
    return control["state"]


def login(hosted):
    state = start_login(hosted)
    client = hosted[0]
    response = client.get("/auth/callback", params={"state": state, "code": "offline-code"}, follow_redirects=False)
    assert response.status_code == 303, response.text
    assert response.headers["location"] == ORIGIN + "/"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    response = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
    assert response.status_code == 200
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]})
    return response


def test_production_missing_authentication_fails_before_provisioning(hosted, monkeypatch):
    _, _, db, _, _, _ = hosted
    monkeypatch.delenv("ARYN_AUTH_MODE")
    with pytest.raises(ValueError):
        create_app(db, IsolatedTestRuntime(), testing=True)
    monkeypatch.setenv("ARYN_AUTH_MODE", "local-development")
    with pytest.raises(ValueError):
        create_app(db, IsolatedTestRuntime(), testing=True)
    with db.session() as session:
        assert session.get(OrganizationModel, DEV_ORG) is None
        assert session.query(MembershipModel).filter_by(user_id=DEV_ACTOR).count() == 0


def test_anonymous_loopback_proxy_cannot_bootstrap_admin(hosted):
    client = hosted[0]
    for headers in ({"Origin": ORIGIN}, {"Origin": ORIGIN, "X-Forwarded-Proto": "https"}):
        response = client.post("/api/session", json={}, headers=headers)
        assert response.status_code == 401
        assert "set-cookie" not in response.headers
    for path in ("/api/workspace", "/api/projects/project/snapshot", "/docs", "/openapi.json", "/debug", "/diagnostics"):
        assert client.get(path).status_code in {401, 404}
    assert client.post("/api/projects/project/runs", json={}, headers={"Origin": ORIGIN, "Accept": "text/event-stream"}).status_code == 401


@pytest.mark.parametrize("headers", [{"Host": "evil.example"}, {"Origin": "https://evil.example"},
    {"Forwarded": "for=127.0.0.1;proto=https"}, {"X-User": "admin"}, {"X-Role": "admin"},
    {"X-Forwarded-User": "admin"}, {"X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https"},
    {"X-Forwarded-Proto": "http"}])
def test_spoofed_network_and_identity_headers_denied(hosted, headers):
    client = hosted[0]
    assert client.post("/api/session", json={}, headers={"Origin": ORIGIN, **headers}).status_code == 403


@pytest.mark.parametrize("claims", [{"iss": "https://evil.example"}, {"aud": "foreign-client"},
    {"exp": 1}, {"iat": int(time.time()) + 86400}, {"nonce": "replayed"}, {"sub": ""},
    {"aud": ["aryn", "other"], "azp": "other"}])
def test_invalid_signed_oidc_claims_fail_closed(hosted, claims):
    hosted[4]["claims"] = claims
    state = start_login(hosted)
    assert hosted[0].get("/auth/callback", params={"state": state, "code": "code"}, follow_redirects=False).status_code == 401
    assert hosted[0].post("/api/session", json={}, headers={"Origin": ORIGIN}).status_code == 401


def test_invalid_signature_state_replay_and_redirect_rejected(hosted):
    client = hosted[0]
    assert client.get("/auth/login?redirect_uri=https://evil.example", follow_redirects=False).status_code == 400
    state = start_login(hosted)
    assert client.get("/auth/callback", params={"state": "forged", "code": "code"}).status_code == 401
    hosted[4]["signing_key"] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401
    hosted[4].pop("signing_key")
    assert client.get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401
    assert client.get("/auth/callback?state=a&state=b&code=c").status_code == 401


def test_verified_subject_requires_provisioned_membership(hosted):
    hosted[4]["claims"] = {"sub": "unprovisioned", "email": "admin@example"}
    state = start_login(hosted)
    assert hosted[0].get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401
    hosted[4]["claims"] = {}
    with hosted[2].session(write=True) as session:
        session.query(MembershipModel).filter_by(user_id="human").delete()
    state = start_login(hosted)
    assert hosted[0].get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401


def test_valid_subject_scoped_core_principal_and_no_browser_escalation(hosted):
    login(hosted)
    client = hosted[0]
    workspace = client.get("/api/workspace")
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["user"] == {"name": "human", "id": "human", "role": "operator"}
    assert [p["id"] for p in workspace.json()["projects"]] == ["project"]
    assert client.get("/api/projects/private/snapshot").status_code == 403
    assert client.get("/api/projects/foreign-project/snapshot").status_code == 403
    assert client.post("/api/projects/project/blueprints", json={"name": "Research", "slug": "research", "role": "admin", "actor_id": "admin"}).status_code == 422
    response = client.post("/api/projects/project/blueprints", json={"name": "Research", "slug": "research"})
    assert response.status_code == 201
    assert response.json()["organization_id"] == "org"
    assert hosted[0].post("/api/session", json={"roles": ["admin"]}).status_code == 422
    snapshot = client.get("/api/projects/project/snapshot").json()
    assert snapshot["permissions"]["version:approve"] is False
    assert snapshot["permissions"]["agent:rollback"] is False
    for secret in (hosted[3].session_secret.get_secret_value(), hosted[3].identity_secret.get_secret_value(), "synthetic-private-access-token"):
        assert secret not in json.dumps(snapshot) + workspace.text


@pytest.mark.parametrize("revocation", ["session", "membership", "identity", "expiry"])
def test_revocation_and_expiry_rechecked_at_core_commit(hosted, revocation):
    login(hosted)
    client, app, db, *_ = hosted
    sid = client.cookies.get(HOSTED_COOKIE)
    token_hash = app.state.authentication.digest("session", sid)
    ctx = app.state.binder.create_trusted_context("human", "org", "project", auth_session_id=token_hash)
    with db.session(write=True) as session:
        if revocation == "session":
            session.get(AuthSessionModel, token_hash).revoked_at = datetime.now(timezone.utc)
        elif revocation == "expiry":
            session.get(AuthSessionModel, token_hash).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif revocation == "membership":
            session.query(MembershipModel).filter_by(user_id="human").update({"status": "revoked"})
        else:
            session.get(ExternalIdentityModel, "external").status = "revoked"
    with pytest.raises(PermissionDeniedError):
        app.state.factory.create_blueprint(ctx, "Denied", "denied")
    assert client.post("/api/projects/project/blueprints", json={"name": "Denied", "slug": "denied"}).status_code in {401, 403}


def test_csrf_logout_fixation_and_cross_browser_callback(hosted):
    login(hosted)
    client = hosted[0]
    old = client.cookies.get(HOSTED_COOKIE)
    state = start_login(hosted)
    cookie = client.cookies.get("__Host-aryn_login")
    client.cookies.delete("__Host-aryn_login")
    assert client.get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401
    client.cookies.set("__Host-aryn_login", cookie, domain="studio.example", path="/")
    assert client.get("/auth/callback", params={"state": state, "code": "code"}, follow_redirects=False).status_code == 303
    assert client.cookies.get(HOSTED_COOKIE) != old
    assert client.post("/api/logout", json={}, headers={"X-CSRF-Token": "bad"}).status_code == 403
    response = client.post("/api/session", json={})
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    assert client.post("/api/logout", json={}).status_code == 200
    assert client.get("/api/workspace").status_code == 401
    client.cookies.set(HOSTED_COOKIE, old, domain="studio.example", path="/")
    assert client.get("/api/workspace").status_code == 401


def test_jwks_rotation_new_key_and_backend_proxy_contract(hosted):
    login(hosted)
    hosted[4].update(key=rsa.generate_private_key(public_exponent=65537, key_size=2048), kid="rotated")
    login(hosted)
    assert hosted[5].count("/jwks") == 2
    client, app, *_ = hosted
    with TestClient(app, base_url="http://studio.example", client=("127.0.0.1", 1)) as backend:
        assert backend.get("/auth/login").status_code == 403
        assert backend.get("/auth/login", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False).status_code == 303
    with TestClient(app, base_url="http://studio.example", client=("192.0.2.10", 1)) as untrusted:
        assert untrusted.get("/auth/login", headers={"X-Forwarded-Proto": "https"}).status_code == 403
    assert client.get("/api/workspace").status_code == 200


def test_configuration_callback_and_secret_validation(hosted):
    data = hosted[3].model_dump()
    for changes in ({"redirect_uri": "https://evil.example/auth/callback"}, {"public_origin": "http://studio.example"},
                    {"trusted_proxies": ("0.0.0.0/0",)}, {"session_secret": ""}, {"identity_secret": ""}):
        with pytest.raises(ValueError):
            AuthenticationSettings(**{**data, **changes})
    assert get_settings().aryn_env == "production"


@pytest.mark.asyncio
async def test_oidc_verifier_accepts_es256_and_rejects_unsigned_or_hmac(hosted):
    from cryptography.hazmat.primitives.asymmetric import ec
    private = ec.generate_private_key(ec.SECP256R1())
    key = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    key.update(kid="ec-key", use="sig", alg="ES256")
    provider = OIDCProvider(hosted[3], httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [key]})))
    claims = {"iss": ISSUER, "sub": "subject-1", "aud": "aryn", "iat": int(time.time()), "exp": int(time.time()) + 300, "nonce": "expected"}
    encoded = jwt.encode(claims, private, algorithm="ES256", headers={"kid": "ec-key"})
    assert (await provider.verify(encoded, "expected"))["sub"] == "subject-1"
    for algorithm, secret in (("none", None), ("HS256", "synthetic-untrusted-signature-secret")):
        with pytest.raises(ValueError):
            await provider.verify(jwt.encode(claims, secret, algorithm=algorithm, headers={"kid": "ec-key"}), "expected")


def test_session_binding_cannot_be_stripped_from_core_context(hosted):
    login(hosted)
    client, app, *_ = hosted
    sid = app.state.authentication.digest("session", client.cookies.get(HOSTED_COOKIE))
    ctx = app.state.binder.create_trusted_context("human", "org", "project", auth_session_id=sid)
    ctx.auth_session_id = None
    assert not app.state.binder.verify_context(ctx).allowed
    with pytest.raises(PermissionDeniedError):
        app.state.factory.create_blueprint(ctx, "Forged", "forged")


def test_authenticated_hosted_governance_run_and_stream_use_core(hosted):
    # Explicit isolated fixture provisioning; login never grants this authority.
    with hosted[2].session(write=True) as session:
        session.query(MembershipModel).filter_by(user_id="human").update({"role": "admin"})
    login(hosted)
    client = hosted[0]
    prefix = "/api/projects/project"
    bp = client.post(prefix + "/blueprints", json={"name": "Research", "slug": "governed"}).json()
    response = client.post(prefix + f"/blueprints/{bp['id']}/versions", json={"version_number": "1.0.0",
        "system_prompt": "Follow research safety guidelines and abstain without evidence.", "model": "test/model-a", "max_tokens": 512})
    assert response.status_code == 201, response.text
    version = response.json()
    response = client.post(prefix + f"/versions/{version['id']}/bench", json={"allow_remote_model": True})
    assert response.status_code == 200 and response.json()["passed"], response.text
    response = client.post(prefix + f"/versions/{version['id']}/approve", json={"payload_hash": version["payload_hash"], "comments": "Reviewed offline signed evidence."})
    assert response.status_code == 200, response.text
    assert client.post(prefix + f"/versions/{version['id']}/publish", json={}).status_code == 200
    response = client.post(prefix + "/assignments", json={"blueprint_id": bp["id"], "version_id": version["id"], "role_name": "Researcher"})
    assert response.status_code == 201, response.text
    assignment = response.json()
    body = {"assignment_id": assignment["id"], "prompt": "Explain liquidity and solvency safely.", "idempotency_key": "hosted-signed-run-one", "allow_remote_model": True}
    response = client.post(prefix + "/runs", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["execution_claim_verified"] and data["assignment_provenance_verified"]
    assert data["agent_version_id"] == version["id"] and data["actual_model"] == "test/model-a"
    assert client.post(prefix + "/runs", json=body).json()["run_id"] == data["run_id"]
    response = client.post(prefix + "/runs", json={**body, "idempotency_key": "hosted-signed-run-two"}, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200 and "event: run.completed" in response.text
    snapshot = client.get(prefix + "/snapshot").json()
    assert snapshot["assignments"][0]["activation_verified"]
    assert snapshot["versions"][0]["governance_valid"]
    assert all(event["actor_type"] == "user" and event["actor_id"] == "human" for event in snapshot["audit"])
    assert all(event["authenticated"] for event in snapshot["audit"])


def test_runtime_credentials_rejected_from_prompt_and_absent_in_diagnostics(hosted, caplog):
    _, app, _, config, *_ = hosted
    login(hosted)
    secret = config.session_secret.get_secret_value()
    assert hosted[0].post("/api/projects/project/runs", json={"prompt": secret}, headers={"Accept": "text/event-stream"}).status_code == 422
    import logging
    logging.getLogger("authentication.diagnostics").warning("secret %s nested %s", secret, {"access_token": "synthetic-token"})
    assert secret not in caplog.text and "synthetic-token" not in caplog.text
    assert app.state.authentication is not None


def test_expired_login_transaction_and_development_mapping_rejected(hosted):
    from database.schema import LoginTransactionModel
    state = start_login(hosted)
    with hosted[2].session(write=True) as session:
        session.query(LoginTransactionModel).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    assert hosted[0].get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401
    with hosted[2].session(write=True) as session:
        session.get(ExternalIdentityModel, "external").actor_id = DEV_ACTOR
    state = start_login(hosted)
    assert hosted[0].get("/auth/callback", params={"state": state, "code": "code"}).status_code == 401


def test_local_requires_explicit_development_and_rejects_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.delenv("ARYN_AUTH_MODE")
    db = DatabaseManager(create_db_engine(f"sqlite:///{(tmp_path / 'local.sqlite3').as_posix()}"))
    init_db(db.engine)
    with pytest.raises(ValueError):
        create_app(db, IsolatedTestRuntime())
    monkeypatch.setenv("ARYN_AUTH_MODE", "local-development")
    app = create_app(db, IsolatedTestRuntime())
    with TestClient(app, base_url="http://127.0.0.1:8710", client=("127.0.0.1", 1)) as client:
        assert client.post("/api/session", json={}, headers={"Origin": "http://127.0.0.1:8710", "X-Forwarded-Proto": "https"}).status_code == 403
        response = client.post("/api/session", json={}, headers={"Origin": "http://127.0.0.1:8710"})
        assert response.status_code == 200 and response.json()["mode"] == "development"
    db.engine.dispose()


def test_api_cli_cannot_override_loopback_binding_to_public_interface(hosted):
    import os
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-m", "services.api", "--host", "0.0.0.0"],
        env=dict(os.environ), capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "loopback address" in result.stderr
    assert hosted[3].session_secret.get_secret_value() not in result.stdout + result.stderr


def test_role_change_after_preflight_and_invalid_csrf_denied(hosted):
    login(hosted)
    client, app, db, *_ = hosted
    token_hash = app.state.authentication.digest("session", client.cookies.get(HOSTED_COOKIE))
    ctx = app.state.binder.create_trusted_context("human", "org", "project", auth_session_id=token_hash)
    permissions = app.state.factory.permission_engine
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(user_id="human").update({"role": "admin"})
    assert permissions.evaluate("version:approve", ctx, "org", "project").allowed
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(user_id="human").update({"role": "operator"})
    with db.session(write=True) as session:
        with pytest.raises(PermissionDeniedError):
            permissions.enforce("version:approve", ctx, "org", "project", session=session)
    assert client.post("/api/logout", json={}, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert "access-control-allow-origin" not in client.get("/api/workspace").headers


def test_server_sessions_persist_without_development_fallback(hosted):
    login(hosted)
    client, _, db, config, *_ = hosted
    sid = client.cookies.get(HOSTED_COOKIE)
    app = create_app(db, IsolatedTestRuntime(), authentication=config, identity_provider=OIDCProvider(config, httpx.MockTransport(lambda _: httpx.Response(500))))
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as restarted:
        restarted.cookies.set(HOSTED_COOKIE, sid, domain="studio.example", path="/")
        assert restarted.get("/api/workspace").json()["user"]["id"] == "human"
