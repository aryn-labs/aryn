"""Deterministic operator UAT model double. No network, credentials or inference."""
import json
import time

from packages.contracts.model import ModelCapabilities
from packages.contracts.runtime import (RuntimeAdapter, RuntimeHealth, RuntimeCapabilities,
    RuntimeModelAvailability, RuntimeTrace, RunResult, RunStatus, RunUsage, ToolCall, ToolTurnResult)
from packages.contracts.tool import GITHUB_ISSUE_TOOL, GitHubUATPlan
from packages.contracts.bench import strict_json_loads, validate_output, OutputContract


class GitHubUATModelDouble(RuntimeAdapter):
    def __init__(self, issue_number):
        self.issue_number = issue_number

    async def health(self):
        return RuntimeHealth(is_healthy=True, status="isolated_double", platform="operator-uat",
            version="1", listener_url="none")

    async def capabilities(self):
        return RuntimeCapabilities(enabled_toolsets=[], available_toolsets=[], tools_confined=True,
            supports_governed_tool_turns=True, details={"execution_source": "isolated_operator_double"})

    async def model_availability(self, model, *, refresh=False):
        return RuntimeModelAvailability(model=model, status="available" if model == "mock-fast" else "unavailable",
            source="isolated_operator_double")

    async def model_capabilities(self, model):
        return ModelCapabilities(model=model, text_generation="supported", tool_calling="supported",
            source="isolated_operator_double")

    async def execute_tool_turn(self, turn, context):
        calls, output = [], ""
        if turn.iteration == 1 and not turn.history and turn.tool_names == [GITHUB_ISSUE_TOOL]:
            calls = [ToolCall(call_id="issue_read", name=GITHUB_ISSUE_TOOL, arguments={"issue_number": self.issue_number})]
        elif turn.iteration == 2 and turn.history:
            data = strict_json_loads(turn.history[-1]["content"])
            # Select only bounded identity/state; never interpret the issue's text.
            output = json.dumps({key: data[key] for key in
                ("repository", "issue_number", "state", "source", "content_trust")})
            plan = GitHubUATPlan(issue_number=self.issue_number, enable_live=True,
                operator_confirmed=True, idempotency_key="double_contract")
            if validate_output(output, OutputContract.model_validate(plan.output_contract()))[0]:
                raise ValueError("UAT continuation did not satisfy its fixed contract.")
        else:
            raise ValueError("UAT double accepts exactly one read and one continuation.")
        return ToolTurnResult(run_id=turn.run_id, iteration=turn.iteration,
            result=RunResult(run_id=f"uat_double_{turn.iteration}", model=turn.request.model,
                requested_model=turn.request.model, actual_model=turn.request.model,
                provider="github-uat-model-double", gateway="9Router", runtime_backend="Hermes",
                status=RunStatus.RUNNING if calls else RunStatus.COMPLETED, output=output,
                usage=RunUsage(input_tokens=20, output_tokens=20, total_tokens=40, cost_usd=0,
                    cost_source="runtime_meter"), created_at=time.time()), tool_calls=calls)

    async def start_run(self, request, context):
        raise NotImplementedError("Operator UAT requires Core governed turns.")

    async def get_result(self, run_id, context):
        raise NotImplementedError("Operator UAT results belong to Core.")

    async def cancel_run(self, run_id, context):
        return False

    async def get_trace(self, run_id, context):
        return RuntimeTrace(run_id=run_id, unavailability_reason="Use signed Core audit.")
