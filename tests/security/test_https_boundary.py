"""Fail-closed socket/TLS boundary with synthetic credentials and no external egress."""
import asyncio
import ipaddress
import socket
import ssl
import time

import pytest
from pydantic import SecretStr, ValidationError

from modules.core.tools import CoreTools
from modules.core.permissions.engine import PermissionDeniedError
from packages.contracts.bench import evidence_hash
from packages.contracts.tool import HTTPSInvocation, https_endpoint
from packages.tool_adapters.https import HTTPSTrust, HTTPSBoundaryError
from tests.https_fixture import ALIAS, definition, https_server as https_server


async def boundary(lifecycle, state):
    _, ctx, _, factory, _, _ = lifecycle
    core = factory.execution_coordinator
    core.mcp_tools = CoreTools(core, https_trust=state.trust)
    approval = await core.mcp_tools.register(ctx, definition(state, ctx), state.secret)
    adapter = core.mcp_tools.current(ctx, ALIAS).adapter
    call = HTTPSInvocation(run_id="run_" + "a" * 32, trace_id=ctx.correlation_id, organization_id="org", project_id="project",
        call_number=1, call_id="read", deadline_at=min(time.time() + 5, approval.expires_at),
        binding_hash=approval.binding_hash, input_hash=evidence_hash({"key": "aryn-core"}))
    call = call.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", call.payload())})
    def reauthorize():
        core.mcp_tools.current(ctx, ALIAS, approval.binding_hash)
    return core, ctx, adapter, call, reauthorize


@pytest.mark.parametrize("value", ["http://example.com:443", "https://u:p@example.com:443", "https://example.com:443/",
    "https://example.com:443?q=1", "https://example.com:443#x", "https://EXAMPLE.com:443", "https://example.com.:443",
    "https://example.com", "https://example.com:0443", "https://example.com:0", "https://example.com:65536",
    "https://example.com\\@127.0.0.1:443", "https://example.com%00:443", "https://example.com\r\n:443",
    "https://127.1:443", "https://2130706433:443", "https://0177.0.0.1:443", "https://0x7f000001:443",
    "https://[::ffff:127.0.0.1]:443", "https://[fe80::1%25eth0]:443", "https://example.local:443",
    "https://example.internal:443", "https://example.localhost:443", "https://éxample.com:443"])
def test_url_ambiguity_and_aliases_are_denied(value):
    with pytest.raises(ValueError):
        https_endpoint(value)


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0", "10.0.0.1", "172.16.1.1", "192.168.1.1", "169.254.169.254",
    "100.100.100.200", "100.64.0.1", "192.0.0.1", "192.0.2.1", "198.18.0.1", "224.0.0.1", "240.1.1.1",
    "255.255.255.255", "168.63.129.16", "64:ff9b::a9fe:a9fe", "64:ff9b:1::a9fe:a9fe",
    "::", "::1", "fc00::1", "fe80::1", "ff02::1", "2001:db8::1", "::ffff:8.8.8.8",
    "2002:0808:0808::1", "2001:0000:4136:e378:8000:63bf:3fff:fdd2"])
def test_production_destination_denies_nonpublic_and_transition_addresses(address):
    trust = HTTPSTrust()
    with pytest.raises(HTTPSBoundaryError):
        trust.check_address(address)


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700:4700::1111"])
def test_canonical_public_addresses_are_classified_without_connection(address):
    assert HTTPSTrust().check_address(address) == str(ipaddress.ip_address(address))


@pytest.mark.parametrize("endpoint", ["https://127.0.0.1:443", "https://[::1]:443", "https://10.0.0.1:443", "https://169.254.169.254:443"])
async def test_production_allowlist_does_not_enable_private_bypass(endpoint):
    trust = HTTPSTrust((endpoint,))
    with pytest.raises(HTTPSBoundaryError):
        await trust.resolve(endpoint)


async def test_default_deny_host_and_port_without_dns(monkeypatch):
    def no_dns(*args, **kwargs):
        pytest.fail("Unapproved destination must not resolve.")
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    trust = HTTPSTrust(("https://api.example.com:443",))
    for endpoint in ("https://api.example.com:444", "https://other.example.com:443"):
        with pytest.raises(HTTPSBoundaryError):
            await trust.resolve(endpoint)


@pytest.mark.parametrize("records", [["8.8.8.8", "127.0.0.1"], ["::1"], ["169.254.169.254"], []])
async def test_dns_entire_answer_must_be_safe(monkeypatch, records):
    loop = asyncio.get_running_loop()
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in records]
    monkeypatch.setattr(loop, "getaddrinfo", resolve)
    trust = HTTPSTrust(("https://api.example.com:443",))
    with pytest.raises(HTTPSBoundaryError):
        await trust.resolve("https://api.example.com:443")


async def test_dns_changes_after_approval_deny_before_socket(lifecycle, https_server, monkeypatch):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    async def changed(endpoint):
        return ("8.8.8.8",)
    monkeypatch.setattr(adapter.trust, "resolve", changed)
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not https_server.requests


@pytest.mark.parametrize("stage", ["dns", "connect", "tls"])
async def test_reauthorization_at_physical_dispatch(lifecycle, https_server, monkeypatch, stage):
    core, ctx, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
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
    else:
        native = asyncio.open_connection
        async def opening(*args, **kwargs):
            result = await native(*args, **kwargs)
            revoke()
            return result
        monkeypatch.setattr(asyncio, "open_connection", opening)
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not https_server.requests


@pytest.mark.parametrize("kind", ["unknown_ca", "hostname", "disabled_verification"])
async def test_tls_verification_is_mandatory(lifecycle, https_server, monkeypatch, kind):
    if kind == "unknown_ca":
        https_server.trust.context = ssl.create_default_context()
    elif kind == "hostname":
        port = https_server.endpoint.rsplit(":", 1)[1]
        https_server.endpoint = f"https://fixture.example:{port}"
        https_server.trust.endpoints = frozenset((https_server.endpoint,))
        async def synthetic_dns(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", int(port)))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", synthetic_dns)
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    if kind == "disabled_verification":
        adapter.trust.context.check_hostname = False
        adapter.trust.context.verify_mode = ssl.CERT_NONE
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not https_server.requests


async def test_proxy_environment_is_never_consulted(lifecycle, https_server, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://169.254.169.254:1")
    monkeypatch.setenv("NO_PROXY", "")
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    data, proof = await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert data["project_id"] == "project" and proof["network_requests"] == len(https_server.requests) == 1


async def test_forged_invocation_denies_before_socket(lifecycle, https_server):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    invocation = invocation.model_copy(update={"attestation": "forged"})
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert not https_server.requests


async def test_invocation_replay_and_rate_limit_do_not_retry(lifecycle, https_server):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert len(https_server.requests) == 1
    adapter._attempts.extend([time.monotonic()] * 12)
    call = invocation.model_copy(update={"call_id": "second"})
    call = call.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", call.payload())})
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, call, core.db_manager.evidence_signer.verify, reauthorize)
    assert len(https_server.requests) == 1


async def test_connection_deadline_and_cancellation_close_without_retry(lifecycle, https_server, monkeypatch):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    entered = asyncio.Event()
    async def stalled(*args):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", stalled)
    invocation = invocation.model_copy(update={"deadline_at": time.time() + .15})
    invocation = invocation.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", invocation.payload())})
    with pytest.raises(TimeoutError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)
    assert entered.is_set() and not https_server.requests


async def test_synchronous_reauthorization_cannot_outlive_dispatch_deadline(lifecycle, https_server):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    # The first check precedes transport timing. Delay the subsequent physical
    # dispatch check past the *adapter* timeout, while Core's deadline is valid.
    spec = adapter.approval.connection.model_copy(update={"timeout_seconds": .05})
    approval = adapter.approval.model_copy(update={"connection": spec})
    approval = approval.model_copy(update={"binding_hash": approval.configuration_hash()})
    approval = approval.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_connection_approval", approval.payload())})
    adapter.approval = approval
    invocation = invocation.model_copy(update={"binding_hash": approval.binding_hash})
    invocation = invocation.model_copy(update={"attestation": core.db_manager.evidence_signer.sign("https_tool_call", invocation.payload())})
    checks = 0
    def delayed_authority():
        nonlocal checks
        checks += 1
        if checks > 1:
            time.sleep(.08)
    with pytest.raises(TimeoutError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, delayed_authority)
    assert checks == 2 and not https_server.requests and not adapter._receipts


async def test_cancellation_after_get_creates_no_success_receipt(lifecycle, https_server):
    core, _, adapter, invocation, reauthorize = await boundary(lifecycle, https_server)
    https_server.mode = "wait"
    task = asyncio.create_task(adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize))
    await asyncio.wait_for(https_server.entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not adapter._receipts and len(https_server.requests) == 1
    with pytest.raises(HTTPSBoundaryError):
        await adapter.invoke({"key": "aryn-core"}, invocation, core.db_manager.evidence_signer.verify, reauthorize)


async def test_registration_requires_human_scope_and_cannot_restore_on_restart(lifecycle, https_server):
    from packages.contracts.core import Actor, ActorType
    from tests.conftest import bind_test_context
    core, ctx, _, _, _ = await boundary(lifecycle, https_server)
    agent = bind_test_context(ctx.model_copy(update={"actor": Actor(actor_id="owner", organization_id="org", actor_type=ActorType.AGENT)}))
    with pytest.raises(PermissionDeniedError):
        await core.mcp_tools.register(agent, definition(https_server, ctx), https_server.secret)
    for field in ("project_id", "organization_id"):
        spec = definition(https_server, ctx.model_copy(update={field: "foreign"}))
        with pytest.raises(PermissionDeniedError):
            await core.mcp_tools.register(ctx, spec, https_server.secret)
    restarted = CoreTools(core, https_trust=https_server.trust)
    with pytest.raises(PermissionDeniedError):
        restarted.current(ctx, ALIAS)


@pytest.mark.parametrize("secret", ["short", "a" * 300, "a" * 40 + "\r\nHost: other", "a" * 40 + " ", "é" * 40])
async def test_untrusted_credential_material_is_rejected(lifecycle, https_server, secret):
    _, ctx, _, factory, _, _ = lifecycle
    tools = CoreTools(factory.execution_coordinator, https_trust=https_server.trust)
    with pytest.raises(PermissionDeniedError):
        await tools.register(ctx, definition(https_server, ctx), SecretStr(secret))
    assert not https_server.requests


@pytest.mark.parametrize("field,value", [("method", "POST"), ("route", "/records/{url}"), ("route", "/records/../{key}"),
    ("route", "/records/{key}?url=x"), ("timeout_seconds", 6), ("max_response_bytes", 999999)])
def test_operator_configuration_cannot_create_generic_executor(lifecycle, https_server, field, value):
    with pytest.raises(ValidationError):
        definition(https_server, lifecycle[1], **{field: value})
