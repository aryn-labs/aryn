"""Native Hermes dispatch in an immutable, bounded Docker worker owned by Core."""
import asyncio
import json
import re
import time
import math

from packages.contracts.bench import evidence_hash
from packages.contracts.tool import checked_data


class NativeBoundaryError(LookupError):
    pass


class NativeWorker:
    def __init__(self, image_id, schemas, *, docker="docker", toolsets=None):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise ValueError("Native worker requires an immutable reviewed image ID.")
        self.image_id = image_id
        self.schemas = dict(schemas)
        self.toolsets = dict(toolsets or {})
        self.docker = docker
        self._workers = {}
        self._changes = asyncio.Lock()

    async def _command(self, arguments, *, payload=None, timeout=10):
        process = await asyncio.create_subprocess_exec(self.docker, *arguments,
            stdin=asyncio.subprocess.PIPE if payload is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        async def collect():
            if payload is not None:
                process.stdin.write(payload)
                await process.stdin.drain()
                process.stdin.close()
            chunks, size = [], 0
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                size += len(chunk)
                if size > 32768:
                    raise NativeBoundaryError("Native sandbox output exceeded its resource limit.")
                chunks.append(chunk)
            await process.wait()
            return b"".join(chunks)
        try:
            stdout = await asyncio.wait_for(collect(), timeout)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode != 0 or len(stdout) > 32768:
            raise NativeBoundaryError("Native sandbox operation failed.")
        return stdout

    def profile(self):
        return {"image_id": self.image_id, "network": "none", "read_only_root": True,
            "user": "65532:65532", "capabilities": "none", "no_new_privileges": True,
            "memory_bytes": 268435456, "cpus": 1, "pids": 64,
            "workspace_bytes": 67108864, "host_mounts": [], "credentials": []}

    async def invoke(self, spec, call, execution, invocation, verifier, reauthorize):
        if (not verifier("native_tool_call", invocation["payload"], invocation["attestation"])
                or invocation["payload"].get("input_hash") != evidence_hash(call.arguments)
                or invocation["payload"].get("sandbox") != self.profile()
                or invocation["payload"].get("run_id") != execution.run_id
                or invocation["payload"].get("organization_id") != execution.organization_id
                or invocation["payload"].get("project_id") != execution.project_id
                or invocation["payload"].get("call_id") != call.call_id
                or invocation["payload"].get("deadline_at") != execution.deadline_at
                or invocation["payload"].get("call_number") != execution.call_number
                or invocation["payload"].get("configuration_hash") != evidence_hash(spec.model_dump(mode="json"))
                or call.arguments != spec.arguments or spec.image_id != self.image_id
                or spec.organization_id != execution.organization_id or spec.project_id != execution.project_id
                or time.time() >= execution.deadline_at or spec.tool_name not in self.schemas):
            raise NativeBoundaryError("Native invocation authority differs.")
        checked_data(call.arguments, self.schemas[spec.tool_name]["parameters"])
        key = evidence_hash([execution.organization_id, execution.project_id, execution.run_id])
        name = "aryn-runtime-" + key[:32]
        async with self._changes:
            reauthorize()
            if key not in self._workers:
                if len(self._workers) >= 16:
                    raise NativeBoundaryError("Native worker concurrency quota exceeded.")
                await self._command(["run", "--detach", "--rm", "--pull", "never", "--name", name, "--network", "none", "--read-only",
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65532:65532",
                    "--memory", "256m", "--memory-swap", "256m", "--cpus", "1", "--pids-limit", "64",
                    "--tmpfs", "/workspace:rw,nosuid,nodev,size=64m,uid=65532,gid=65532",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m", "--tmpfs", "/home/runtime:rw,nosuid,nodev,size=16m,uid=65532,gid=65532",
                    "--workdir", "/workspace", "--env", "HERMES_HOME=/home/runtime",
                    "--env", "TERMINAL_ENV=local", "--env", "TERMINAL_CWD=/workspace",
                    "--entrypoint", "sleep", self.image_id, str(max(1, math.ceil(execution.deadline_at - time.time())))])
                self._workers[key] = name
            reauthorize()
            seconds = min(30, execution.deadline_at - time.time())
            if seconds <= 0:
                raise NativeBoundaryError("Native execution deadline expired.")
            try:
                data = await self._command(["exec", "--interactive", name, "python", "/opt/aryn/native_worker.py"],
                    payload=json.dumps({"name": spec.tool_name, "arguments": call.arguments,
                        "task_id": key}).encode(), timeout=seconds)
                result = json.loads(data)
                if set(result) != {"text"} or not isinstance(result["text"], str):
                    raise NativeBoundaryError("Native result contract differs.")
                reauthorize()
                return result, {"sandbox": self.profile(), "invocation_hash": evidence_hash(invocation),
                    "run_id": execution.run_id, "organization_id": execution.organization_id,
                    "project_id": execution.project_id, "call_id": call.call_id,
                    "input_hash": evidence_hash(call.arguments), "output_hash": evidence_hash(result)}
            except BaseException:
                await self._remove(key, name)
                raise

    async def _remove(self, key, name):
        await self._command(["rm", "--force", name])
        self._workers.pop(key, None)

    async def close_run(self, execution):
        key = evidence_hash([execution.organization_id, execution.project_id, execution.run_id])
        if name := self._workers.get(key):
            await self._remove(key, name)
