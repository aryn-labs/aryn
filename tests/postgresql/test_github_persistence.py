"""Restricted PostgreSQL writer, actual TLS and the existing signed Core history."""
import json

import pytest

from database.repositories.audit_repo import AuditRepository
from database.schema import AuditEventModel, RunStateModel
from packages.contracts.runtime import RunStatus
from tests.github_fixture import github_server as github_server, https_server as https_server
from tests.integration.test_github_tools import published_github

pytestmark = pytest.mark.postgresql


async def test_github_evidence_scope_budget_and_idempotency(hosted_lifecycle, github_server):
    db, ctx, runtime, core, assignment, approval, _ = await published_github(hosted_lifecycle, github_server)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "postgres-github")
    assert result.status == RunStatus.COMPLETED and result.execution_claim_verified and result.assignment_provenance_verified
    assert len(github_server.requests) == 1 and len(runtime.turns) == 2
    assert await core.get_managed_result(result.run_id, ctx) == result
    assert await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "postgres-github") == result
    assert len(github_server.requests) == 1
    with db.session() as session:
        row = session.get(RunStateModel, result.run_id)
        assert row.usage_settled and row.reserved_tokens == 0
        assert json.loads(row.effective_limits_json)["https_bindings"] == {approval.connection.declaration.name: approval.binding_hash}
        events = session.query(AuditEventModel).filter_by(resource_id=result.run_id).all()
        assert events and all(AuditRepository(session).verify_authenticated_event(event) for event in events)
    core.mcp_tools.revoke(ctx, approval.connection.connection_id)
    assert await core.get_managed_result(result.run_id, ctx) == result
