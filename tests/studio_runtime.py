"""Explicitly isolated test double. Never imported by the production API."""

import time

from packages.contracts.runtime import (
    RunResult,
    RunStatus,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeTrace,
    RunUsage,
)


class IsolatedTestRuntime(RuntimeAdapter):
    def __init__(self):
        self.requests = []
        self.fail = False
        self.online = True
        self.tools = []
        self.status = RunStatus.COMPLETED

    async def health(self):
        return RuntimeHealth(
            is_healthy=self.online,
            status="ok",
            platform="isolated-test",
            version="test-only",
            listener_url="isolated",
        )

    async def capabilities(self):
        return RuntimeCapabilities(
            enabled_toolsets=self.tools,
            available_toolsets=[],
            tools_confined=not self.tools,
        )

    async def execute_direct_turn(self, request, context):
        self.requests.append(request)
        prompt = request.prompt
        if self.fail:
            output = "PWNED_BY_INJECTION"
        elif "System override" in prompt:
            output = "I cannot ignore research safety guidelines."
        elif "cat /etc/shadow" in prompt:
            output = "I do not have access to terminal operations."
        elif "Nebula-XYZ" in prompt:
            output = "Records are unavailable. I must abstain for an invalid date."
        elif "liquidity" in prompt:
            output = "Liquidity covers short-term cash obligations; solvency covers long-term debt."
        else:
            output = "[PENGUJIAN TERISOLASI] Likuiditas berkaitan dengan kewajiban jangka pendek; solvabilitas berkaitan dengan kemampuan jangka panjang."
        return RunResult(
            run_id=f"test_{len(self.requests)}",
            status=self.status,
            output=output,
            model=request.model,
            usage=RunUsage(input_tokens=20, output_tokens=30, total_tokens=50),
            created_at=time.time(),
            completed_at=time.time(),
        )

    async def start_run(self, request, context):
        return "test_only"

    async def get_result(self, run_id, context):
        raise NotImplementedError("Tests use direct turns")

    async def cancel_run(self, run_id, context):
        return False

    async def get_trace(self, run_id, context):
        return RuntimeTrace(run_id=run_id)
