"""Protocol I/O double for governance regressions; never a real-service proof."""

import copy
import json
import time
from services.api.studio import DEV_ORG, DEV_PROJECT
from packages.tool_adapters.operational import OperationalTargets


class OperationalProtocolDouble(OperationalTargets):
    def __init__(self):
        binding = {"binding_id": "test_disposable_service", "environment_id": "e" * 32,
            "organization_id": DEV_ORG, "project_id": DEV_PROJECT,
            "container_id": "a" * 64, "image_id": "sha256:" + "b" * 64,
            "profile": {"network": "none", "read_only_root": True, "user": "65532:65532",
                "memory_bytes": 134217728, "nano_cpus": 500000000, "pids": 64}}
        super().__init__({"targets": [binding]})
        self.state = {"instance": "c" * 32, "generation": 1, "running": True,
            "blocking_fault": False, "child_instance": "d" * 32,
            "last_execution_id": None, "expires_at": time.time() + 3600}
        self.effects = []
        self.inspect_data = {"Id": binding["container_id"], "Image": binding["image_id"],
            "State": {"Running": True}, "Mounts": [], "NetworkSettings": {"Networks": {"none": {}}},
            "Config": {"User": "65532:65532", "Env": ["PATH=/usr/local/bin:/usr/bin"],
                "Entrypoint": ["python", "-B", "/opt/aryn/operational_service.py"], "Cmd": ["serve", "--ttl", "3600"],
                "Labels": {"aryn.operational.environment": binding["environment_id"],
                    "aryn.organization": DEV_ORG, "aryn.project": DEV_PROJECT}},
            "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
                "Binds": None, "Tmpfs": None, "PublishAllPorts": False, "UsernsMode": "", "PortBindings": {},
                "Devices": [], "CapAdd": [], "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                "PidMode": "", "IpcMode": "private", "Memory": 134217728, "MemorySwap": 134217728,
                "NanoCpus": 500000000, "PidsLimit": 64}}

    def fault(self, *, blocking=False):
        self.state.update(running=False, blocking_fault=blocking, generation=self.state["generation"] + 1,
            last_execution_id=None)

    def command(self, arguments, *, payload=None, timeout=10):
        if arguments[0] == "inspect":
            return json.dumps([self.inspect_data]).encode()
        if arguments[:2] == ["image", "inspect"]:
            return json.dumps([{"Config": {"Env": self.inspect_data["Config"]["Env"]}}]).encode()
        if arguments[-1] == "observe":
            running, fault = self.state["running"], self.state["blocking_fault"]
            return json.dumps({"controller_status": 200, "controller": copy.deepcopy(self.state),
                "business_status": (503 if fault else 200) if running else None,
                "business": {"instance": self.state["child_instance"], "healthy": not fault, "requests": 1} if running else None,
                "business_available": running, "healthy": running and not fault,
                "observed_at": time.time(), "latency_ms": 0.25}).encode()
        if arguments[-1] == "control":
            data = json.loads(payload)
            assert data["action"] == "restart_service" and data["instance"] == self.state["instance"]
            assert data["generation"] == self.state["generation"] and not self.state["running"]
            assert time.time() < data["deadline_at"]
            self.effects.append(data)
            self.state.update(running=True, generation=self.state["generation"] + 1,
                child_instance=data["execution_id"], last_execution_id=data["execution_id"])
            return json.dumps(self.state).encode()
        raise AssertionError("Unreviewed protocol command.")
