"""Trusted fixed Docker boundary for registered disposable services.

Only Core receives this adapter. No Docker socket, host path, command, URL or
server credential is exposed to a model or browser. Dispatch requires an exact
Core signature and live reauthorization immediately before the external effect.
"""

import asyncio
import json
import time
from packages.contracts.bench import evidence_hash
from packages.contracts.operational import OperationalBindings, ServiceProbe, ControllerState
from packages.tool_adapters.native import DockerTransport, NativeBoundaryError


class OperationalBoundaryError(NativeBoundaryError):
    pass


class OperationalTargets:
    def __init__(self, manifest, *, docker="docker"):
        config = OperationalBindings.model_validate(manifest)
        self.bindings = {item.binding_id: item.model_dump(mode="json") for item in config.targets}
        # Reuse the existing bounded Docker subprocess transport, not its tools.
        self.transport = DockerTransport(docker=docker)

    def command(self, arguments, *, payload=None, timeout=10):
        return asyncio.run(self.transport._command(arguments, payload=payload, timeout=timeout))

    def binding(self, ctx, identifier):
        binding = self.bindings.get(identifier)
        if not binding or (binding["organization_id"], binding["project_id"]) != (
                ctx.organization_id, ctx.project_id):
            raise OperationalBoundaryError("Scoped operational binding is unavailable.")
        return binding

    def inspect(self, binding):
        data = json.loads(self.command(["inspect", binding["container_id"]]))
        if not isinstance(data, list) or len(data) != 1:
            raise OperationalBoundaryError("Operational inspection differs.")
        item = data[0]
        host, config, profile = item["HostConfig"], item["Config"], binding["profile"]
        if (item["Id"] != binding["container_id"] or item["Image"] != binding["image_id"]
                or not item["State"]["Running"]
                or config["Labels"].get("aryn.operational.environment") != binding["environment_id"]
                or config["Labels"].get("aryn.organization") != binding["organization_id"]
                or config["Labels"].get("aryn.project") != binding["project_id"]
                or host["NetworkMode"] != "none" or not host["ReadonlyRootfs"]
                or config["User"] != profile["user"] or host["Privileged"] or item["Mounts"]
                or host.get("Binds") or host.get("Tmpfs") or host.get("PublishAllPorts")
                or host.get("UsernsMode") == "host" or set(item["NetworkSettings"]["Networks"]) != {"none"}
                or host["PortBindings"] or host["Devices"] or host["CapAdd"]
                or host["CapDrop"] != ["ALL"] or host["SecurityOpt"] != ["no-new-privileges"]
                or host["PidMode"] or host["IpcMode"] == "host"
                or host["Memory"] != profile["memory_bytes"] or host["MemorySwap"] != profile["memory_bytes"]
                or host["NanoCpus"] != profile["nano_cpus"] or host["PidsLimit"] != profile["pids"]
                or config["Entrypoint"] != ["python", "-B", "/opt/aryn/operational_service.py"]
                or len(config["Cmd"]) != 3 or config["Cmd"][:2] != ["serve", "--ttl"]
                or not config["Cmd"][2].isdigit() or not 30 <= int(config["Cmd"][2]) <= 28800):
            raise OperationalBoundaryError("Disposable target isolation or identity differs.")
        image = json.loads(self.command(["image", "inspect", binding["image_id"]]))[0]
        if (config["Env"] != image["Config"]["Env"]
                or config.get("Healthcheck") != image["Config"].get("Healthcheck")):
            raise OperationalBoundaryError("Disposable target environment was overridden.")

    def observe(self, ctx, binding_id):
        binding = self.binding(ctx, binding_id)
        self.inspect(binding)
        result = ServiceProbe.model_validate(json.loads(self.command(["exec", binding["container_id"],
            "python", "-B", "/opt/aryn/operational_service.py", "observe"])))
        if abs(time.time() - result.observed_at) > 10 or result.controller.expires_at <= time.time():
            raise OperationalBoundaryError("Operational measurement is expired.")
        return result.model_dump(mode="json")

    def dispatch(self, ctx, binding_id, admission, verifier, reauthorize):
        binding = self.binding(ctx, binding_id)
        payload = admission["payload"]
        if (not verifier("relay_operational_action", payload, admission["attestation"])
                or payload.get("organization_id") != ctx.organization_id
                or payload.get("project_id") != ctx.project_id
                or payload.get("binding_hash") != evidence_hash(binding)
                or payload.get("action") != "restart_service"
                or not time.time() < payload.get("deadline_at", 0) <= time.time() + 15):
            raise OperationalBoundaryError("Exact Core action admission is unavailable.")
        self.inspect(binding)
        reauthorize()
        command = {key: payload[key] for key in ("action", "instance", "generation", "execution_id", "deadline_at")}
        # Transport ambiguity is an unknown outcome. This boundary never retries.
        result = ControllerState.model_validate(json.loads(self.command(["exec", "--interactive",
            binding["container_id"], "python", "-B", "/opt/aryn/operational_service.py", "control"],
            payload=json.dumps(command).encode(), timeout=max(0.01, payload["deadline_at"] - time.time()))))
        return {"binding_hash": evidence_hash(binding), "admission_hash": evidence_hash(admission),
            "output": result.model_dump(mode="json"), "observed_at": time.time()}
