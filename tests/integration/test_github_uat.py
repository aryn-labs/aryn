"""Human UAT profile through Core and actual local TLS, never GitHub's API."""
import asyncio
import json
from pathlib import Path
import time

import pytest
from pydantic import SecretStr, ValidationError

from modules.core.permissions.engine import PermissionDeniedError
from modules.core.tools import CoreTools
from packages.contracts.runtime import RunRequest, RunStatus, RunUsage, ModelIdentityError
from packages.contracts.tool import GitHubUATPlan, GITHUB_ISSUE_TOOL as ALIAS
from packages.runtime_adapters.github_uat import GitHubUATModelDouble
from scripts import github_uat as uat
from tests.conftest import bind_test_context
from tests.github_fixture import definition, github_server as github_server, https_server as https_server
from tests.unit.test_github_uat_config import TOKEN, write_config


def plan(**updates):
    return GitHubUATPlan(**{"issue_number": 42, "enable_live": True, "operator_confirmed": True,
        "idempotency_key": "operator_uat", **updates})


async def approved(lifecycle, state):
    db, ctx, _, factory, _, _ = lifecycle
    core = factory.execution_coordinator
    core.runtime_adapter = GitHubUATModelDouble(42)
    core.mcp_tools = CoreTools(core, https_trust=state.trust)
    approval = await core.mcp_tools.register(ctx, definition(state, ctx, calls_per_minute=1), state.secret)
    return db, ctx, core, approval


async def test_human_profile_actual_tls_single_read_signed_evidence_and_idempotency(lifecycle, github_server, caplog):
    db, ctx, core, approval = await approved(lifecycle, github_server)
    result = await core.execute_github_uat(plan(), ctx)
    assert result.status == RunStatus.COMPLETED and result.execution_claim_verified
    assert result.assignment_id is None and result.agent_version_id is None and not result.assignment_provenance_verified
    assert result.effective_limits["tool_grants"] == [ALIAS] and result.effective_limits["max_tool_calls"] == 1
    assert result.effective_limits["max_turns"] == 2 and result.usage.cost_usd == 0
    summary = await uat._verified_summary(db, ctx, core, result, approval)
    assert summary["status"] == "VERIFIED" and summary["signed_execution_verified"]
    assert summary["source"] == "github_https_fixture" and summary["network_requests"] == 1
    assert github_server.requests[0]["line"] == "GET /repos/aryn-labs/aryn/issues/42 HTTP/1.1"
    assert github_server.requests[0]["tls"] in {"TLSv1.2", "TLSv1.3"}
    assert await core.execute_github_uat(plan(), ctx) == result and len(github_server.requests) == 1
    artifacts = json.dumps(summary) + result.model_dump_json() + caplog.text
    artifacts += str(core.audit_logger.get_events_for_correlation(ctx.correlation_id, ctx))
    assert github_server.secret.get_secret_value() not in artifacts
    assert github_server.secret.get_secret_value().encode() not in Path(db.engine.url.database).read_bytes()


@pytest.mark.parametrize("field,value", [("enable_live", False), ("operator_confirmed", False),
    ("issue_number", 0), ("issue_number", True), ("issue_number", "42"), ("repository", "other/private")])
async def test_core_revalidates_operator_plan_before_dispatch(lifecycle, github_server, field, value):
    _, ctx, core, _ = await approved(lifecycle, github_server)
    forged = plan().model_copy(update={field: value})
    with pytest.raises(ValidationError):
        await core.execute_github_uat(forged, ctx)
    assert not github_server.requests


@pytest.mark.parametrize("scope", ["agent", "tenant", "project", "identity", "runtime", "viewer", "owner"])
async def test_operator_identity_and_scope_are_current(lifecycle, github_server, scope):
    from packages.contracts.core import ActorType
    _, ctx, core, _ = await approved(lifecycle, github_server)
    if scope == "agent":
        ctx = bind_test_context(ctx.model_copy(update={"actor": ctx.actor.model_copy(update={"actor_type": ActorType.AGENT})}))
    elif scope == "identity":
        ctx = ctx.model_copy(update={"identity_token": "forged"})
    elif scope == "runtime":
        core.runtime_adapter.issue_number = 43
    elif scope in {"viewer", "owner"}:
        from database.repositories.organization_repo import OrganizationRepository
        with core.db_manager.session() as session:
            OrganizationRepository(session).add_member(ctx.organization_id, "different_human", "viewer" if scope == "viewer" else "admin")
        ctx = bind_test_context(ctx.model_copy(update={"actor": ctx.actor.model_copy(update={"actor_id": "different_human"})}))
    else:
        ctx = bind_test_context(ctx.model_copy(update={"organization_id" if scope == "tenant" else "project_id": "foreign"}))
    with pytest.raises(PermissionDeniedError):
        await core.execute_github_uat(plan(), ctx)
    assert not github_server.requests


@pytest.mark.parametrize("change", ["revoked", "expired", "rotated"])
async def test_approval_reauthorization_before_physical_dispatch(lifecycle, github_server, monkeypatch, change):
    _, ctx, core, _ = await approved(lifecycle, github_server)
    native = core.runtime_adapter.execute_tool_turn
    async def turn(*args):
        result = await native(*args)
        if change == "expired":
            monkeypatch.setattr("modules.core.tools.clock", lambda: time.time() + 301)
        else:
            core.mcp_tools.revoke(ctx, "github_issues")
            if change == "rotated":
                github_server.secret = SecretStr("rotated-synthetic-github-credential-123456")
                await core.mcp_tools.register(ctx, definition(github_server, ctx, calls_per_minute=1), github_server.secret)
        return result
    monkeypatch.setattr(core.runtime_adapter, "execute_tool_turn", turn)
    with pytest.raises(PermissionDeniedError):
        await core.execute_github_uat(plan(), ctx)
    assert not github_server.requests


async def test_metadata_cannot_upgrade_ordinary_run_to_operator_profile(lifecycle, github_server):
    _, ctx, core, _ = await approved(lifecycle, github_server)
    with pytest.raises(PermissionDeniedError):
        await core.execute_managed_direct_turn(plan().request(), ctx)
    request = RunRequest(prompt="Read", model="mock-fast", metadata={"github_operator_uat": plan().model_dump()})
    with pytest.raises(NotImplementedError):
        # Direct execution has no governed grant; the isolated UAT runtime does
        # not implement direct inference and cannot convert metadata to authority.
        await core.execute_managed_direct_turn(request, ctx)
    assert not github_server.requests


@pytest.mark.parametrize("mutation", ["number", "extra", "provider", "model", "no_request"])
async def test_double_cannot_forge_request_scope_identity_or_success(lifecycle, github_server, monkeypatch, mutation):
    _, ctx, core, _ = await approved(lifecycle, github_server)
    native = core.runtime_adapter.execute_tool_turn
    async def turn(*args):
        result = await native(*args)
        if mutation == "provider":
            result.result.provider = "unexpected-provider"
        elif mutation == "model":
            result.result.actual_model = "different-model"
        elif mutation == "no_request":
            result.tool_calls = []
            result.result.status = RunStatus.COMPLETED
        else:
            result.tool_calls[0].arguments = {"issue_number": 43} if mutation == "number" else {"issue_number": 42, "repository": "other/private"}
        return result
    monkeypatch.setattr(core.runtime_adapter, "execute_tool_turn", turn)
    if mutation in {"provider", "model"}:
        with pytest.raises(ModelIdentityError):
            await core.execute_github_uat(plan(), ctx)
    else:
        result = await core.execute_github_uat(plan(), ctx)
        assert result.status == RunStatus.FAILED and not result.execution_evidence["actions"]
    assert not github_server.requests


@pytest.mark.parametrize("mode,code", [("injection", None), ("unauthorized", "github_unauthorized"),
    ("forbidden", "github_forbidden"), ("rate_limited", "github_rate_limited"), ("secret", "uat_response_invalid"),
    ("pull_request", "uat_response_invalid"), ("wrong_repo", "uat_response_invalid"), ("truncated", "uat_response_invalid")])
async def test_owner_runner_uses_existing_core_transport_and_cleans_binding(github_server, monkeypatch, caplog, mode, code):
    github_server.secret = SecretStr(TOKEN)
    github_server.mode = mode
    native = uat._build_core
    captured = []
    def isolated(config):
        db, ctx, core = native(config)
        core.mcp_tools = CoreTools(core, https_trust=github_server.trust)
        captured.append(core)
        return db, ctx, core
    monkeypatch.setattr(uat, "_build_core", isolated)
    monkeypatch.setattr(uat, "_definition", lambda ctx: definition(github_server, ctx, calls_per_minute=1))
    report = await uat.run_uat(uat.UATConfig(plan(), SecretStr(TOKEN)))
    assert report["credential_revoked"] and not captured[0].mcp_tools._entries
    assert not captured[0].authority.valid and len(github_server.requests) == 1
    assert TOKEN not in json.dumps(report) + caplog.text
    if code:
        assert report["status"] == "FAILED" and report["error_code"] == code and "signed_execution_verified" not in report
    else:
        assert report["status"] == "VERIFIED" and report["source"] == "github_https_fixture"
        assert "title" not in report and "body_excerpt" not in report and report["paid_inference"] is False


async def test_owner_cli_disabled_gate_makes_no_dns_or_core(tmp_path, monkeypatch, capsys):
    path = write_config(tmp_path, {"ARYN_GITHUB_UAT_ENABLE_LIVE": "0", "ARYN_GITHUB_UAT_TOKEN": TOKEN})
    monkeypatch.setattr(uat, "ENV_FILE", path)
    def no_core(*args):
        pytest.fail("A disabled live gate must not construct Core or resolve GitHub.")
    monkeypatch.setattr(uat, "_build_core", no_core)
    assert await asyncio.to_thread(uat.main, ["--confirm-live-github-read"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "uat_live_gate_disabled"


async def test_missing_binding_and_budget_exhaustion_cannot_dispatch(lifecycle, github_server, monkeypatch):
    core = lifecycle[3].execution_coordinator
    core.runtime_adapter = GitHubUATModelDouble(42)
    with pytest.raises(PermissionDeniedError):
        await core.execute_github_uat(plan(), lifecycle[1])
    _, ctx, core, _ = await approved(lifecycle, github_server)
    native = core.runtime_adapter.execute_tool_turn
    async def exhausted(*args):
        value = await native(*args)
        value.result.usage = RunUsage(input_tokens=100000, output_tokens=5, total_tokens=100005)
        return value
    monkeypatch.setattr(core.runtime_adapter, "execute_tool_turn", exhausted)
    result = await core.execute_github_uat(plan(), ctx)
    assert result.status == RunStatus.FAILED and result.error_code == "execution_limit_exceeded"
    assert not github_server.requests


async def test_operator_cancellation_fences_continuation_and_duplicate_in_flight(lifecycle, github_server, monkeypatch):
    from modules.core.workflows.coordinator import RunInProgressError
    _, ctx, core, _ = await approved(lifecycle, github_server)
    entered, release, identities = asyncio.Event(), asyncio.Event(), []
    native = core.runtime_adapter.execute_tool_turn
    async def waiting(turn, context):
        identities.append(turn.run_id)
        entered.set()
        await release.wait()
        return await native(turn, context)
    monkeypatch.setattr(core.runtime_adapter, "execute_tool_turn", waiting)
    task = asyncio.create_task(core.execute_github_uat(plan(), ctx))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        with pytest.raises(RunInProgressError):
            await core.execute_github_uat(plan(), ctx)
        assert not await core.cancel_managed_run(identities[0], ctx)
    finally:
        release.set()
    with pytest.raises(PermissionDeniedError):
        await task
    assert not github_server.requests


async def test_continuation_must_match_validated_issue_not_forge_source(lifecycle, github_server, monkeypatch):
    _, ctx, core, _ = await approved(lifecycle, github_server)
    native = core.runtime_adapter.execute_tool_turn
    async def forged(*args):
        value = await native(*args)
        if value.iteration == 2:
            data = json.loads(value.result.output)
            data["source"], data["state"] = "github_https", "closed"
            value.result.output = json.dumps(data)
        return value
    monkeypatch.setattr(core.runtime_adapter, "execute_tool_turn", forged)
    result = await core.execute_github_uat(plan(), ctx)
    assert result.status == RunStatus.FAILED and result.error_code == "tool_input_invalid"
    assert len(github_server.requests) == 1


async def test_owner_cli_actual_loopback_tls_and_sanitized_summary(tmp_path, github_server, monkeypatch, capsys):
    github_server.secret = SecretStr(TOKEN)
    monkeypatch.setattr(uat, "ENV_FILE", write_config(tmp_path))
    native = uat._build_core
    def fixture_core(config):
        db, context, core = native(config)
        core.mcp_tools = CoreTools(core, https_trust=github_server.trust)
        return db, context, core
    monkeypatch.setattr(uat, "_build_core", fixture_core)
    monkeypatch.setattr(uat, "_definition", lambda ctx: definition(github_server, ctx, calls_per_minute=1))
    loop = asyncio.get_running_loop()
    # Reuse the fixture loop: Windows event-loop creation uses a separate local
    # wakeup socketpair, which the existing exact-port fixture guard denies.
    # Only scheduling is bridged; Core and the TLS socket execute unchanged.
    monkeypatch.setattr(uat.asyncio, "run", lambda coroutine:
        asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=15))
    assert await asyncio.to_thread(uat.main, ["--confirm-live-github-read"]) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "VERIFIED" and report["source"] == "github_https_fixture"
    assert report["credential_revoked"] and report["network_requests"] == len(github_server.requests) == 1
    assert TOKEN not in output.out + output.err


@pytest.mark.parametrize("change", ["repository", "rate_profile"])
async def test_other_registered_repository_or_broad_rate_profile_is_denied(lifecycle, github_server, change):
    from packages.contracts.tool import github_issue_output
    _, ctx, _, factory, _, _ = lifecycle
    core = factory.execution_coordinator
    core.runtime_adapter = GitHubUATModelDouble(42)
    core.mcp_tools = CoreTools(core, https_trust=github_server.trust)
    updates = {"calls_per_minute": 12} if change == "rate_profile" else {
        "calls_per_minute": 1, "repository_owner": "other", "repository_name": "private",
        "route": "/repos/other/private/issues/{key}",
        "output_schema": github_issue_output(ctx.organization_id, ctx.project_id, "other", "private")}
    await core.mcp_tools.register(ctx, definition(github_server, ctx, **updates), github_server.secret)
    with pytest.raises(PermissionDeniedError):
        await core.execute_github_uat(plan(), ctx)
    assert not github_server.requests


async def test_forged_completion_evidence_rejected_by_owner_summary(lifecycle, github_server):
    db, ctx, core, approval = await approved(lifecycle, github_server)
    result = await core.execute_github_uat(plan(), ctx)
    forged = result.model_copy(deep=True)
    forged.execution_evidence["actions"] = []
    with pytest.raises(uat.UATError, match="uat_evidence_invalid"):
        await uat._verified_summary(db, ctx, core, forged, approval)
    assert len(github_server.requests) == 1


async def test_unexpected_local_error_containing_secret_is_sanitized(monkeypatch, caplog):
    def fail(config):
        raise RuntimeError(TOKEN)
    monkeypatch.setattr(uat, "_build_core", fail)
    report = await uat.run_uat(uat.UATConfig(plan(), SecretStr(TOKEN)))
    assert report == {"status": "FAILED", "error_code": "uat_failed", "retry": False}
    assert TOKEN not in json.dumps(report) + caplog.text


async def test_tls_failure_is_classified_without_disabling_verification(github_server, monkeypatch):
    import ssl
    github_server.secret = SecretStr(TOKEN)
    github_server.trust.context = ssl.create_default_context()
    native = uat._build_core
    def fixture_core(config):
        db, context, core = native(config)
        core.mcp_tools = CoreTools(core, https_trust=github_server.trust)
        return db, context, core
    monkeypatch.setattr(uat, "_build_core", fixture_core)
    monkeypatch.setattr(uat, "_definition", lambda ctx: definition(github_server, ctx, calls_per_minute=1))
    report = await uat.run_uat(uat.UATConfig(plan(), SecretStr(TOKEN)))
    assert report["status"] == "FAILED" and report["error_code"] == "uat_tls_unverified"
    assert report["credential_revoked"] and not github_server.requests


async def test_owner_task_interruption_revokes_credential_and_disposes_state(github_server, monkeypatch):
    github_server.secret = SecretStr(TOKEN)
    github_server.mode = "wait"
    native = uat._build_core
    captured = []
    def fixture_core(config):
        db, context, core = native(config)
        core.mcp_tools = CoreTools(core, https_trust=github_server.trust)
        captured.append(core)
        return db, context, core
    monkeypatch.setattr(uat, "_build_core", fixture_core)
    monkeypatch.setattr(uat, "_definition", lambda ctx: definition(github_server, ctx, calls_per_minute=1))
    task = asyncio.create_task(uat.run_uat(uat.UATConfig(plan(), SecretStr(TOKEN))))
    await asyncio.wait_for(github_server.entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(github_server.requests) == 1 and not captured[0].mcp_tools._entries
    assert not captured[0].authority.valid


async def test_summary_rechecks_binding_after_core_completion(lifecycle, github_server):
    db, ctx, core, approval = await approved(lifecycle, github_server)
    result = await core.execute_github_uat(plan(), ctx)
    core.mcp_tools.revoke(ctx, approval.connection.connection_id)
    with pytest.raises(PermissionDeniedError):
        await uat._verified_summary(db, ctx, core, result, approval)
    assert len(github_server.requests) == 1
