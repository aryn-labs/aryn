"""Real restricted PostgreSQL writer, synthetic HTTPS fixture and model double."""
import json

import pytest
from sqlalchemy import text

from tests.https_fixture import https_server as https_server
from tests.integration.test_https_tools import published_https

pytestmark = pytest.mark.postgresql


async def test_https_claim_evidence_budget_and_idempotency(hosted_lifecycle, https_server):
    from database.repositories.run_state_repo import RunStateRepository
    from database.repositories.budget_repo import BudgetRepository
    db, ctx, runtime, core, assignment, approval, _ = await published_https(hosted_lifecycle, https_server)
    result = await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "postgres-https")
    assert result.status.value == "completed" and result.execution_claim_verified
    assert len(https_server.requests) == 1 and len(runtime.turns) == 2
    assert await core.get_managed_result(result.run_id, ctx) == result
    assert (await core.get_managed_trace(result.run_id, ctx)).available
    assert await core.execute_assigned_agent_turn(assignment.id, "Read.", ctx, "postgres-https") == result
    assert len(https_server.requests) == 1
    with db.session() as session:
        row = RunStateRepository(session).get_run(ctx, result.run_id)
        assert row.usage_settled and row.reserved_tokens == 0 and row.total_tokens == 30
        assert json.loads(row.effective_limits_json)["https_bindings"] == {approval.connection.declaration.name: approval.binding_hash}
        assert BudgetRepository(session).get_budget(ctx).reserved_tokens == 0
        assert not session.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")).scalar()
