"""Real hosted HTTPS boundary with offline OIDC and isolated runtime, never public deployment evidence."""

import asyncio
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from database.schema import (
    MembershipModel,
    AutomationOccurrenceModel,
    AutomationDefinitionModel,
)
from tests.security.test_deployment_authentication import (
    hosted as hosted,
    login,
    ORIGIN,
)
from tests.integration.test_studio_api import draft, promoted, PREFIX, studio as studio


@pytest.fixture
def ingress_hosted(monkeypatch, request):
    monkeypatch.setenv("ARYN_WEBHOOK_INGRESS_ORIGIN", ORIGIN)
    value = request.getfixturevalue("hosted")
    client, app, db, *_ = value
    login(value)
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(
            organization_id="org", user_id="human"
        ).update({"role": "admin"})

    class Scoped:
        def post(self, path, **kwargs):
            return client.post(path.replace(PREFIX, "/api/projects/project"), **kwargs)

    bp, version = draft(Scoped(), "webhook-agent")
    assignment = promoted(Scoped(), bp, version)
    root = "/api/projects/project/automations"
    configuration = dict(
        title="Governed HTTPS signal",
        input="Fixed reviewed input",
        allow_remote_model=True,
        target=dict(
            kind="agent",
            id=assignment["id"],
            version_id=version["id"],
            payload_hash=version["payload_hash"],
            activation_id=assignment["current_transition_id"],
        ),
        schedule=dict(kind="webhook", start_at=datetime.now(timezone.utc).isoformat()),
    )
    response = client.post(root, json=configuration)
    assert response.status_code == 201, response.text
    definition = response.json()
    url = root + "/" + definition["id"]
    assert (
        client.post(
            url + "/approve",
            json=dict(
                expected_revision=1,
                payload_hash=definition["payload_hash"],
                reason="Review fixed input and scoped TLS signal",
            ),
        ).status_code
        == 200
    )
    assert (
        client.post(
            url + "/state", json=dict(expected_revision=1, enabled=True)
        ).status_code
        == 200
    )
    credential = client.post(
        url + "/webhook", json=dict(expected_revision=1, action="rotate")
    ).json()
    external = TestClient(app, base_url=ORIGIN, client=("192.0.2.10", 1234))
    try:
        yield client, external, app, db, definition, credential, configuration
    finally:
        external.close()


def send(value, event_id="example-event", **kwargs):
    _, client, _, _, _, credential, _ = value
    headers = {
        "Authorization": "Bearer " + credential["secret"],
        "X-ARYN-Timestamp": datetime.now(timezone.utc).isoformat(),
    }
    headers.update(kwargs.pop("headers", {}))
    return client.post(
        credential["url"],
        json={"event_id": event_id, "event": "trigger"},
        headers=headers,
        **kwargs,
    )


def test_authenticated_https_creates_once_uses_reviewed_input_and_no_secret_read(
    ingress_hosted,
):
    client, _, app, db, definition, credential, _ = ingress_hosted
    before = len(app.state.coordinator.runtime_adapter.requests)
    response = send(ingress_hosted)
    assert response.status_code == 202, response.text
    duplicate = send(ingress_hosted)
    assert duplicate.status_code == 200 and not duplicate.json()["accepted"]
    assert duplicate.json()["occurrence_id"] == response.json()["occurrence_id"]
    asyncio.run(app.state.automations.tick())
    with db.session() as session:
        row = session.get(AutomationOccurrenceModel, response.json()["occurrence_id"])
        payload = json.loads(row.details_json)
        assert row.status == "completed" and payload["run_id"]
        stored = session.get(AutomationDefinitionModel, definition["id"]).details_json
        assert credential["secret"] not in stored
    runtime = app.state.coordinator.runtime_adapter
    assert (
        len(runtime.requests) == before + 1
        and runtime.requests[-1].prompt == "Fixed reviewed input"
    )
    for suffix in ("", "/events", "/occurrences"):
        public = client.get(
            "/api/projects/project/automations/" + definition["id"] + suffix
        ).text
        assert (
            credential["secret"] not in public
            and "token_hash" not in public
            and "webhook_credential" not in public
        )


@pytest.mark.parametrize(
    "attack,expected",
    [
        ("missing", 401),
        ("invalid", 401),
        ("expired", 401),
        ("future", 401),
        ("origin", 403),
        ("cookie", 403),
        ("foreign-host", 403),
        ("content-type", 415),
        ("oversize", 413),
        ("malformed", 422),
        ("duplicate-keys", 422),
        ("target-override", 422),
        ("command", 422),
    ],
)
def test_webhook_transport_authentication_payload_and_authority_denials(
    ingress_hosted, attack, expected
):
    _, client, app, _, _, credential, _ = ingress_hosted
    before = len(app.state.coordinator.runtime_adapter.requests)
    headers = {
        "Authorization": "Bearer " + credential["secret"],
        "X-ARYN-Timestamp": datetime.now(timezone.utc).isoformat(),
        "Content-Type": "application/json",
    }
    payload = json.dumps({"event_id": "denied", "event": "trigger"})
    if attack == "missing":
        headers.pop("Authorization")
    elif attack == "invalid":
        headers["Authorization"] = "Bearer " + "x" * 43
    elif attack == "expired":
        headers["X-ARYN-Timestamp"] = "2020-01-01T00:00:00Z"
    elif attack == "future":
        headers["X-ARYN-Timestamp"] = "2099-01-01T00:00:00Z"
    elif attack == "origin":
        headers["Origin"] = ORIGIN
    elif attack == "cookie":
        headers["Cookie"] = "credential=forged"
    elif attack == "foreign-host":
        headers["Host"] = "foreign.example"
    elif attack == "content-type":
        headers["Content-Type"] = "text/plain"
    elif attack == "oversize":
        payload = "x" * 4097
    elif attack == "malformed":
        payload = "{broken"
    elif attack == "duplicate-keys":
        payload = '{"event_id":"one","event_id":"two","event":"trigger"}'
    else:
        payload = json.dumps(
            {
                "event_id": "denied",
                "event": "trigger",
                "target" if attack == "target-override" else "command": "forged",
            }
        )
    response = client.post(credential["url"], content=payload, headers=headers)
    assert response.status_code == expected, response.text
    assert credential["secret"] not in response.text
    assert len(app.state.coordinator.runtime_adapter.requests) == before


def test_rotation_revocation_pause_edit_and_rate_limits(ingress_hosted):
    client, _, _, _, definition, credential, body = ingress_hosted
    url = "/api/projects/project/automations/" + definition["id"]
    assert (
        client.post(
            url + "/webhook",
            json={"expected_revision": 1, "action": "rotate"},
            headers={"X-CSRF-Token": "bad"},
        ).status_code
        == 403
    )
    rotated = client.post(
        url + "/webhook", json={"expected_revision": 1, "action": "rotate"}
    ).json()
    assert send(ingress_hosted).status_code == 401
    credential.update(rotated)
    assert send(ingress_hosted, "first").status_code == 202
    assert (
        client.post(
            url + "/state", json={"expected_revision": 1, "enabled": False}
        ).status_code
        == 200
    )
    assert send(ingress_hosted, "paused").status_code == 409
    assert (
        client.post(
            url + "/state", json={"expected_revision": 1, "enabled": True}
        ).status_code
        == 200
    )
    for index in range(11):
        assert send(ingress_hosted, "rate-" + str(index)).status_code == 202
    assert send(ingress_hosted, "too-many").status_code == 429
    assert (
        send(ingress_hosted, "first").status_code == 200
    )  # Dedup does not consume a new budget.
    assert (
        client.post(
            url + "/webhook", json={"expected_revision": 1, "action": "revoke"}
        ).status_code
        == 200
    )
    assert send(ingress_hosted, "revoked").status_code == 401
    rotated = client.post(
        url + "/webhook", json={"expected_revision": 1, "action": "rotate"}
    ).json()
    credential.update(rotated)
    edited = client.post(
        url, json={**body, "title": "Revised signal", "expected_revision": 1}
    )
    assert edited.status_code == 200 and edited.json()["status"] == "paused"
    assert send(ingress_hosted, "stale-config").status_code == 401
    assert not client.get(url).json()["approval_verified"]


def test_concurrent_signal_commits_one_occurrence_and_revoked_owner_denied(
    ingress_hosted,
):
    _, _, app, db, _, _, _ = ingress_hosted
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: send(ingress_hosted, "concurrent"), range(2))
        )
    assert sorted(response.status_code for response in responses) == [200, 202]
    assert len({response.json()["occurrence_id"] for response in responses}) == 1
    with db.session(write=True) as session:
        session.query(MembershipModel).filter_by(
            organization_id="org", user_id="human"
        ).update({"status": "revoked"})
    before = len(app.state.coordinator.runtime_adapter.requests)
    assert send(ingress_hosted, "owner-revoked").status_code == 403
    assert len(app.state.coordinator.runtime_adapter.requests) == before


def test_tls_proxy_boundary_does_not_trust_caller_forwarding(ingress_hosted):
    _, external, app, _, _, credential, _ = ingress_hosted
    url = credential["url"].replace("https://", "http://")
    headers = {
        "Authorization": "Bearer " + credential["secret"],
        "X-ARYN-Timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body = {"event_id": "tls-proxy", "event": "trigger"}
    assert external.post(url, json=body, headers=headers).status_code == 403
    assert (
        external.post(
            url, json=body, headers={**headers, "X-Forwarded-Proto": "https"}
        ).status_code
        == 403
    )
    with TestClient(
        app, base_url="http://studio.example", client=("127.0.0.1", 1234)
    ) as trusted:
        response = trusted.post(
            url, json=body, headers={**headers, "X-Forwarded-Proto": "https"}
        )
        assert response.status_code == 202, response.text


def test_local_remains_unavailable_even_when_https_setting_is_supplied(
    monkeypatch, request
):
    monkeypatch.setenv("ARYN_WEBHOOK_INGRESS_ORIGIN", ORIGIN)
    client, _, runtime, _ = request.getfixturevalue("studio")
    assert not client.get(PREFIX + "/automation-triggers").json()["webhook_available"]
    assert (
        client.post(
            "/ingress/webhooks/opaque", json={"event_id": "local", "event": "trigger"}
        ).status_code
        == 503
    )
    assert client.get("/ingress/webhooks/opaque").status_code == 404
    assert not runtime.requests


def test_configured_ingress_origin_must_match_hosted_authentication_before_startup(
    hosted, monkeypatch
):
    from services.api.studio import create_app
    from tests.studio_runtime import IsolatedTestRuntime

    client, _, db, config, *_ = hosted
    monkeypatch.setenv("ARYN_WEBHOOK_INGRESS_ORIGIN", "https://foreign.example")
    runtime = IsolatedTestRuntime()
    with pytest.raises(ValueError, match="Webhook ingress must match"):
        create_app(db, runtime, authentication=config)
    assert not runtime.requests
    login(hosted)
    assert client.get("/api/workspace/context").status_code == 200


def test_webhook_completed_occurrence_survives_recovery_without_duplicate_dispatch(ingress_hosted):
    _, _, app, db, _, _, _ = ingress_hosted
    first = send(ingress_hosted, "recovery-event")
    assert first.status_code == 202
    asyncio.run(app.state.automations.tick())
    before = len(app.state.coordinator.runtime_adapter.requests)
    app.state.automations.recover()
    duplicate = send(ingress_hosted, "recovery-event")
    assert duplicate.status_code == 200 and duplicate.json()["occurrence_id"] == first.json()["occurrence_id"]
    asyncio.run(app.state.automations.tick())
    assert len(app.state.coordinator.runtime_adapter.requests) == before
    with db.session() as session:
        occurrence = session.get(AutomationOccurrenceModel, first.json()["occurrence_id"])
        ctx = app.state.binder.create_trusted_context("human", "org", "project")
        _, verified = app.state.automations.get(session, AutomationOccurrenceModel, ctx, occurrence.id)
        assert occurrence.status == verified["status"] == "completed"
