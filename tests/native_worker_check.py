"""Opt-in real Docker/Hermes tool verification, with a labeled offline model double."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time

from database.connection import DatabaseManager, create_db_engine
from database.schema import Base, AgentVersionModel
from database.repositories.organization_repo import OrganizationRepository
from modules.agent_factory.service import AgentFactoryService
from modules.bench.runner import BenchRunner
from modules.core.identity.binder import TrustedIdentityBinder
from modules.core.permissions.engine import PermissionEngine
from packages.contracts.core import Actor, SecurityContext
from packages.contracts.native_tool import NativeToolReview
from packages.contracts.model import ModelCapabilities
from packages.contracts.runtime import RunRequest, RunResult, RunStatus, RunUsage, ToolCall, ToolTurnResult
from packages.tool_adapters.native import NativeWorker
from tests.model_fixtures import offline_model_router
from tests.studio_runtime import IsolatedTestRuntime


class NativeModelDouble(IsolatedTestRuntime):
    def __init__(self, name, arguments, sequence=None):
        super().__init__()
        self.name, self.arguments = name, arguments
        self.observed = None
        self.sequence = sequence or [(name, arguments)]

    async def capabilities(self):
        caps = await super().capabilities()
        caps.supports_governed_tool_turns = True
        return caps

    async def model_capabilities(self, model):
        return ModelCapabilities(model=model, tool_calling="supported", source="isolated_model_double")

    async def execute_tool_turn(self, turn, context):
        index = turn.iteration - 1
        calls = ([ToolCall(call_id="native_action_" + str(index), name=self.sequence[index][0], arguments=self.sequence[index][1])]
            if index < len(self.sequence) else [])
        if turn.history:
            self.observed = json.loads(turn.history[-1]["content"])
        result = RunResult(run_id="isolated_native_model", status=RunStatus.RUNNING if calls else RunStatus.COMPLETED,
            output="" if calls else "Native tool result verified in offline model continuation.", model=turn.request.model,
            requested_model=turn.request.model, actual_model=turn.request.model, gateway="9Router", runtime_backend="Hermes", provider="isolated-native-model-double",
            usage=RunUsage(input_tokens=10, output_tokens=10, total_tokens=20), created_at=time.time())
        return ToolTurnResult(run_id=turn.run_id, iteration=turn.iteration, result=result, tool_calls=calls)


async def verify(manifest):
    worker = NativeWorker(manifest["image_id"], manifest["schemas"], toolsets=manifest.get("toolsets", {}))
    with tempfile.TemporaryDirectory(prefix="aryn-native-verification-") as directory:
        engine = create_db_engine("sqlite:///" + (Path(directory) / "verification.sqlite3").as_posix())
        with engine.begin() as connection:
            connection.exec_driver_sql("BEGIN")
            Base.metadata.create_all(connection)
        db = DatabaseManager(engine)
        binder = TrustedIdentityBinder(secret_key=b"native-offline-verification-authority-32-bytes")
        ctx = binder.bind_context(SecurityContext(actor=Actor(actor_id="owner", organization_id="org"), organization_id="org", project_id="project"))
        permissions = PermissionEngine(db_manager=db, identity_binder=binder)
        with db.session(write=True) as session:
            repo = OrganizationRepository(session)
            repo.create_organization("org", "Offline verification", "offline")
            repo.add_member("org", "owner", "admin")
            repo.create_project(ctx, "project", "Offline", "offline")
        observations = []
        cases = [([("terminal", {"command": "printf ARYN_NATIVE_SANDBOX"})], "ARYN_NATIVE_SANDBOX", RunStatus.COMPLETED),
            ([("write_file", {"path": "/workspace/native.txt", "content": "ARYN_SCOPED_FILE"}),
                ("read_file", {"path": "/workspace/native.txt"}),
                ("patch", {"path": "/workspace/native.txt", "old_string": "ARYN_SCOPED_FILE", "new_string": "ARYN_PATCHED_FILE"}),
                ("search_files", {"pattern": "ARYN_PATCHED_FILE", "path": "/workspace", "target": "content"}),
                ("read_file", {"path": "/workspace/native.txt"})], "ARYN_PATCHED_FILE", RunStatus.COMPLETED),
            ([("terminal", {"command": "python -c \"import os,socket; assert not any('API_KEY' in k for k in os.environ); s=socket.socket(); s.settimeout(1); assert s.connect_ex(('1.1.1.1',443)) != 0; print('ARYN_NETWORK_DENIED')\""})], "ARYN_NETWORK_DENIED", RunStatus.COMPLETED),
            ([("write_file", {"path": "/etc/aryn-forbidden.txt", "content": "denied"})], None, RunStatus.FAILED),
            ([("read_file", {"path": "/workspace/native.txt"})], None, RunStatus.FAILED)]
        for index, (steps, marker, expected_status) in enumerate(cases):
            sequence = [("aryn_native_" + name, arguments) for name, arguments in steps]
            runtime = NativeModelDouble(*sequence[0], sequence=sequence)
            factory = AgentFactoryService(db, BenchRunner(runtime), permission_engine=permissions, model_router=offline_model_router())
            core = factory.execution_coordinator
            core.mcp_tools.native_worker = worker
            bindings = {}
            for step, (name, arguments) in enumerate(steps):
                if "aryn_native_" + name in bindings:
                    continue
                approval = core.mcp_tools.register_native(ctx, NativeToolReview(connection_id=f"review_{index}_{step}",
                    tool_name=name, arguments=arguments, ttl_seconds=300))
                bindings["aryn_native_" + name] = approval["binding_hash"]
            blueprint = factory.create_blueprint(ctx, "Native verification " + str(index), "native_" + str(index))
            version = factory.create_version(ctx, blueprint.id, "1.0.0", "Use exactly the reviewed isolated native action.", "mock-fast",
                tool_grants=list(bindings), metadata={"native_bindings": bindings,
                    "hermes": {"environment": "isolated_worker", "toolsets": sorted({manifest["schemas"][name]["x_hermes_toolset"] for name, _ in steps})}})
            with db.session(write=True) as session:
                session.get(AgentVersionModel, version.id).status = "evaluating"
            result = await core.execute_bench_agent_turn(RunRequest(prompt="Execute the reviewed native action.", model="mock-fast",
                max_tokens=128, max_total_tokens=4096), ctx, version, list(bindings))
            assert result.status == expected_status, result.model_dump()
            if expected_status == RunStatus.COMPLETED:
                assert [action["tool"] for action in result.execution_evidence["actions"]] == [name for name, _ in sequence]
                assert runtime.observed and (marker is None or marker in runtime.observed["text"])
            else:
                assert result.error_code == "tool_failed" and not result.output
            assert not worker._workers, "Run completion must remove the isolated container."
            observations.append({"tools": list(bindings), "run_id": result.run_id, "status": result.status.value,
                "expected_status": expected_status.value,
                "signed_evidence": result.execution_evidence, "model": "isolated_test_double"})
        engine.dispose()
    print(json.dumps({"native_hermes_sandbox": "PASS", "source_revision": manifest["source_revision"],
        "image_id": manifest["image_id"], "provider_inference": False, "observations": observations}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(verify(json.loads(args.manifest.read_text(encoding="utf-8"))))
