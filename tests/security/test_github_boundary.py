"""GitHub-specific contract/admission checks retain the existing TLS/SSRF boundary."""
import asyncio
import json
import socket
import ssl
import time

import pytest
from pydantic import ValidationError

from modules.core.tools import CoreTools
from modules.core.permissions.engine import PermissionDeniedError
from packages.contracts.bench import evidence_hash
from packages.contracts.tool import GITHUB_API_ORIGIN, GITHUB_ISSUE_TOOL as ALIAS, HTTPSInvocation
from packages.tool_adapters.https import HTTPSBoundaryError, HTTPSTrust
from tests.github_fixture import definition, github_server as github_server, https_server as https_server


async def boundary(lifecycle, state, **updates):
    _, ctx, _, factory, _, _ = lifecycle
    core = factory.execution_coordinator
    core.mcp_tools = CoreTools(core, https_trust=state.trust)
    approval = await core.mcp_tools.register(ctx, definition(state, ctx, **updates), state.secret)
    adapter = core.mcp_tools.current(ctx, ALIAS).adapter
    call = HTTPSInvocation(run_id="run_" + "a" * 32, trace_id=ctx.correlation_id, organization_id="org", project_id="project",
        call_number=1, call_id="read_issue", deadline_at=min(time.time() + 5, approval.expires_at),
        binding_hash=approval.binding_hash, input_hash=evidence_hash({"issue_number": 42}))
    call = call.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", call.payload())})
    def reauthorize():
        core.mcp_tools.current(ctx, ALIAS, approval.binding_hash)
    return core, ctx, adapter, call, reauthorize


@pytest.mark.parametrize("field,value", [("method", "POST"), ("route", "/repos/other/private/issues/{key}"),
    ("route", "/repos/aryn-labs/aryn/issues/{key}?url=x"), ("repository_owner", "other"), ("repository_name", "other"),
    ("repository_owner", "ARYN-labs"), ("repository_name", "../private"), ("repository_name", "a%2fb"),
    ("repository_owner", "a\r\nHost: other"), ("response_profile", "unreviewed"), ("output_schema", {"type": "object"})])
def test_repository_route_method_and_schema_are_exact(lifecycle, github_server, field, value):
    with pytest.raises(ValidationError):
        definition(github_server, lifecycle[1], **{field: value})


@pytest.mark.parametrize("endpoint", ["https://github.com:443", "https://api.github.com:444", "https://api.example.com:443",
    "https://127.0.0.1:443", "https://[::1]:443", "https://169.254.169.254:443"])
async def test_production_github_origin_is_fixed_even_if_allowlisted(lifecycle, github_server, monkeypatch, endpoint):
    def no_dns(*args, **kwargs):
        pytest.fail("Unapproved GitHub origin must not resolve.")
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    _, ctx, _, factory, _, _ = lifecycle
    tools = CoreTools(factory.execution_coordinator, https_endpoints=(endpoint,))
    with pytest.raises(HTTPSBoundaryError):
        await tools.register(ctx, definition(github_server, ctx, endpoint=endpoint), github_server.secret)
    assert not github_server.requests


def test_official_origin_classification_makes_no_connection():
    trust = HTTPSTrust((GITHUB_API_ORIGIN,))
    assert trust.check_service_origin(GITHUB_API_ORIGIN, GITHUB_API_ORIGIN) is None


@pytest.mark.parametrize("stage", ["dns", "connect", "tls", "response"])
async def test_revocation_at_physical_boundaries_denies(lifecycle, github_server, monkeypatch, stage):
    core, ctx, adapter, invocation, reauthorize = await boundary(lifecycle, github_server)
    def revoke():
        core.mcp_tools.revoke(ctx, adapter.approval.connection.connection_id)
    if stage == "dns":
        native = adapter.trust.resolve
        async def resolving(*args):
            result = await native(*args)
            revoke()
            return result
        monkeypatch.setattr(adapter.trust, "resolve", resolving)
    elif stage == "connect":
        loop = asyncio.get_running_loop()
        native = loop.sock_connect
        async def connecting(*args):
            await native(*args)
            revoke()
        monkeypatch.setattr(loop, "sock_connect", connecting)
    elif stage == "tls":
        native = asyncio.open_connection
        async def opening(*args, **kwargs):
            result = await native(*args, **kwargs)
            revoke()
            return result
        monkeypatch.setattr(asyncio, "open_connection", opening)
    else:
        native = github_server.payload_factory
        def payload(mode):
            revoke()
            return native(mode)
        github_server.payload_factory = payload
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert len(github_server.requests) == (1 if stage == "response" else 0) and not adapter._receipts


@pytest.mark.parametrize("addresses", [("8.8.8.8",), ("::1",), ("169.254.169.254",), ("127.0.0.1", "8.8.8.8"), ()])
async def test_dns_drift_denies_before_socket(lifecycle, github_server, monkeypatch, addresses):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, github_server)
    async def resolve(endpoint):
        return addresses
    monkeypatch.setattr(adapter.trust, "resolve", resolve)
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not github_server.requests


@pytest.mark.parametrize("kind", ["unknown_ca", "disabled_verification", "trust_drift"])
async def test_tls_verification_and_approval_trust_are_required(lifecycle, github_server, kind):
    if kind == "unknown_ca":
        github_server.trust.context = ssl.create_default_context()
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, github_server)
    if kind == "disabled_verification":
        adapter.trust.context.check_hostname = False
        adapter.trust.context.verify_mode = ssl.CERT_NONE
    elif kind == "trust_drift":
        adapter.trust.context = ssl.create_default_context()
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not github_server.requests


async def test_proxy_environment_does_not_affect_pinned_socket(lifecycle, github_server, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://169.254.169.254:1")
    monkeypatch.setenv("NO_PROXY", "")
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, github_server)
    data, proof = await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert data["source"] == "github_https_fixture" and proof["network_requests"] == len(github_server.requests) == 1


@pytest.mark.parametrize("field,value", [("attestation", "forged"), ("organization_id", "foreign"),
    ("project_id", "foreign"), ("binding_hash", "0" * 64), ("input_hash", "0" * 64)])
async def test_forged_invocation_never_sends_http(lifecycle, github_server, field, value):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, github_server)
    invocation = invocation.model_copy(update={field: value})
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not github_server.requests and not adapter._receipts


async def test_duplicate_and_rate_budget_are_enforced_without_retry(lifecycle, github_server):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, github_server, calls_per_minute=1)
    await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    invocation = invocation.model_copy(update={"call_id": "second_issue"})
    invocation = invocation.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", invocation.payload())})
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert len(github_server.requests) == 1


@pytest.mark.parametrize("phase", ["connect", "response"])
async def test_timeout_and_cancel_have_no_success_receipt(lifecycle, github_server, monkeypatch, phase):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, github_server)
    if phase == "connect":
        async def stall(*args):
            await asyncio.Event().wait()
        monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", stall)
        invocation = invocation.model_copy(update={"deadline_at": time.time() + .15})
        invocation = invocation.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", invocation.payload())})
        with pytest.raises(TimeoutError):
            await adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
        assert not github_server.requests
    else:
        github_server.mode = "wait"
        task = asyncio.create_task(adapter.invoke({"issue_number": 42}, invocation, core.db_manager.evidence_signer.verify, reauthorize))
        await asyncio.wait_for(github_server.entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(github_server.requests) == 1
    assert not adapter._receipts


async def test_registration_is_human_scoped_and_restart_loses_binding(lifecycle, github_server):
    from packages.contracts.core import Actor, ActorType
    from tests.conftest import bind_test_context
    core, ctx, _, _, _ = await boundary(lifecycle, github_server)
    agent = bind_test_context(ctx.model_copy(update={"actor": Actor(actor_id="owner", organization_id="org", actor_type=ActorType.AGENT)}))
    for other in (agent, bind_test_context(ctx.model_copy(update={"project_id": "foreign"})),
            bind_test_context(ctx.model_copy(update={"organization_id": "foreign"}))):
        with pytest.raises(PermissionDeniedError):
            await core.mcp_tools.register(other, definition(github_server, ctx), github_server.secret)
    fresh = CoreTools(core, https_trust=github_server.trust)
    with pytest.raises(PermissionDeniedError):
        fresh.current(ctx, ALIAS)
    assert not github_server.requests


async def test_diagnostic_redaction_survives_revocation(lifecycle, github_server, caplog):
    import logging
    core, ctx, adapter, _, _ = await boundary(lifecycle, github_server)
    core.mcp_tools.revoke(ctx, adapter.approval.connection.connection_id)
    secret = github_server.secret.get_secret_value()
    logging.getLogger("aryn.github.test").warning("Synthetic reflection %s", secret)
    assert secret not in caplog.text and "[REDACTED]" in caplog.text
    assert secret not in json.dumps(core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx), default=str)
