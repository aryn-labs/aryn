"""Session-scoped MCP approvals under existing Core identity, owner and audit.

No persisted secrets or automatic restoration: restart loses approvals and denies
old bindings. AgentVersion metadata authenticates the exact approval binding.
"""
from __future__ import annotations

import time
import uuid
import threading
from dataclasses import dataclass

from pydantic import SecretStr

from modules.core.permissions.engine import PermissionDeniedError
from modules.core.errors import sanitize
from packages.contracts.bench import evidence_hash
from packages.contracts.core import AuditStatus
from packages.contracts.tool import MCPApproval, MCPInvocation, MCPResultEvidence, MCPServerDefinition, checked_data, loopback_endpoint
from packages.tool_adapters.mcp import MCPAdapter


def clock():
    return time.time()


@dataclass
class ApprovedMCP:
    approval: MCPApproval
    adapter: MCPAdapter
    owner_context: object


class MCPTools:
    def __init__(self, core, approved_endpoints=()):
        self.core = core
        self._endpoints = frozenset(loopback_endpoint(url) for url in approved_endpoints)
        self._entries = {}
        self._changes = threading.RLock()

    def _connection_identity(self, binding_id, secret):
        return evidence_hash(self.core.db_manager.evidence_signer.sign("mcp_connection",
            {"binding_id": binding_id, "secret": secret.get_secret_value()}))

    def _manage(self, context):
        self.core._fence()
        self.core.permission_engine.enforce("tool:register", context, context.organization_id, context.project_id)

    async def register(self, context, definition: MCPServerDefinition, secret: SecretStr, *, ttl_seconds=300):
        self._manage(context)
        spec = MCPServerDefinition.model_validate_json(definition.model_dump_json())
        if (spec.organization_id != context.organization_id or spec.project_id != context.project_id
                or spec.owner_id != context.actor.actor_id or spec.endpoint not in self._endpoints
                or spec.risk != "READ_ONLY" or not spec.enabled or type(ttl_seconds) is not int
                or not 1 <= ttl_seconds <= 300 or not isinstance(secret, SecretStr)
                or len(secret.get_secret_value()) < 32
                or sanitize(spec.model_dump(mode="json"), credentials=(secret.get_secret_value(),)) != spec.model_dump(mode="json")):
            raise PermissionDeniedError("MCP registration is outside the approved read-only scope.")
        key = (spec.organization_id, spec.project_id, spec.declaration.name)
        if key in self._entries or len(self._entries) >= 128 or any(
                entry.approval.server.server_id == spec.server_id
                and entry.approval.server.organization_id == spec.organization_id
                and entry.approval.server.project_id == spec.project_id for entry in self._entries.values()):
            raise PermissionDeniedError("MCP identity is already registered; revoke before replacement.")
        binding = uuid.uuid4().hex
        connection_identity = self._connection_identity(binding, secret)
        observed_at = clock()
        approval = MCPApproval(server=spec, binding_id=binding,
            connection_identity=connection_identity,
            binding_hash=evidence_hash({"server": spec.model_dump(mode="json"), "binding_id": binding,
                "connection_identity": connection_identity}),
            observed_at=observed_at, expires_at=observed_at + ttl_seconds)
        adapter = MCPAdapter(approval, secret)
        await adapter.discover()
        with self._changes:
            self._manage(context)
            if key in self._entries or clock() >= approval.expires_at or any(
                    item.approval.server.server_id == spec.server_id
                    and item.approval.server.organization_id == spec.organization_id
                    and item.approval.server.project_id == spec.project_id for item in self._entries.values()):
                raise PermissionDeniedError("MCP registration authority changed during discovery.")
            approval = approval.model_copy(update={"attestation": self.core.db_manager.evidence_signer.sign(
                "mcp_server_approval", approval.payload())})
            adapter.approval = MCPApproval.model_validate_json(approval.model_dump_json())
            self.core.audit_logger.record("core.mcp.registered", context, spec.server_id, AuditStatus.ALLOWED,
                {"binding_hash": approval.binding_hash, "schema_hash": spec.schema_hash,
                 "tool_name": spec.declaration.name, "remote_tool": spec.tool_name, "risk": spec.risk,
                 "endpoint_hash": evidence_hash(spec.endpoint), "protocol": approval.protocol,
                 "expires_at": approval.expires_at, "source": "authenticated_loopback_mcp"})
            self._entries[key] = ApprovedMCP(approval, adapter, context.model_copy(deep=True))
        return MCPApproval.model_validate_json(approval.model_dump_json())

    def revoke(self, context, server_id):
        self._manage(context)
        with self._changes:
            key = next((key for key, value in self._entries.items()
                if key[:2] == (context.organization_id, context.project_id)
                and value.approval.server.server_id == server_id), None)
            if key is None or self._entries[key].approval.server.owner_id != context.actor.actor_id:
                raise PermissionDeniedError("MCP registration unavailable in this scope.")
            entry = self._entries[key]
            self.core.audit_logger.record("core.mcp.revoked", context, server_id, AuditStatus.COMPLETED,
                {"binding_hash": entry.approval.binding_hash})
            del self._entries[key]

    def _valid(self, entry):
        approval = entry.approval
        if (not approval.server.enabled or approval.server.risk != "READ_ONLY"
                or not approval.observed_at <= clock() < approval.expires_at <= approval.observed_at + 300
                or clock() - approval.observed_at > 60
                or approval.configuration_hash() != approval.binding_hash
                or entry.adapter.approval != approval
                or not entry.adapter.connection_matches(approval.connection_identity,
                    lambda secret: self._connection_identity(approval.binding_id, secret))
                or not self.core.db_manager.evidence_signer.verify(
                    "mcp_server_approval", approval.payload(), approval.attestation)):
            raise PermissionDeniedError("MCP approval is expired, stale or unverified.")
        # Read the owner separately: avoid acquiring a second membership write
        # lock in inverse order to the run actor's existing Core claim lock.
        self.core.permission_engine.enforce("tool:register", entry.owner_context,
            approval.server.organization_id, approval.server.project_id)

    def current(self, context, name, binding_hash=None, *, session=None):
        self.core._fence()
        self.core.permission_engine.enforce("run:create", context,
            context.organization_id, context.project_id, session=session)
        entry = self._entries.get((context.organization_id, context.project_id, name))
        if entry is None or binding_hash is not None and entry.approval.binding_hash != binding_hash:
            raise PermissionDeniedError("Exact MCP tool binding is unavailable.")
        self._valid(entry)
        return entry

    def pins(self, context, version, grants, *, session=None):
        from packages.tool_adapters.fixture import NAME
        names = set(grants) - {NAME}
        if not names:
            return {}
        bindings = version.metadata.get("mcp_bindings", {})
        if (not isinstance(bindings, dict) or set(bindings) != set(version.tool_grants) - {NAME}
                or len(grants) > 1 or any(not isinstance(value, str) for value in bindings.values())
                or version.tool_policy.network_access or version.tool_policy.file_write_access
                or version.tool_policy.code_execution):
            raise PermissionDeniedError("Version must bind one approved MCP read-only tool without host grants.")
        return {name: self.current(context, name, bindings.get(name), session=session).approval.binding_hash for name in names}

    async def invoke(self, context, call, execution_context, binding_hash, reauthorize):
        entry = self.current(context, call.name, binding_hash)
        checked_data(call.arguments, entry.approval.server.declaration.input_schema)
        invocation = MCPInvocation(**execution_context.model_dump(), call_id=call.call_id,
            binding_hash=binding_hash, input_hash=evidence_hash(call.arguments))
        invocation = invocation.model_copy(update={"deadline_at": min(invocation.deadline_at, entry.approval.expires_at)})
        invocation = invocation.model_copy(update={"attestation": self.core.db_manager.evidence_signer.sign(
            "mcp_tool_call", invocation.payload())})
        data, evidence = await entry.adapter.invoke(call.arguments, invocation,
            self.core.db_manager.evidence_signer.verify, reauthorize)
        evidence = MCPResultEvidence.model_validate(evidence).model_dump(mode="json")
        self.current(context, call.name, binding_hash)
        checked_data(data, entry.approval.server.output_schema)
        if (evidence.get("run_id") != invocation.run_id or evidence.get("call_id") != call.call_id
                or evidence.get("binding_hash") != binding_hash or evidence.get("output_hash") != evidence_hash(data)
                or evidence.get("organization_id") != context.organization_id or evidence.get("project_id") != context.project_id
                or evidence["server_id"] != entry.approval.server.server_id
                or evidence["server_name"] != entry.approval.server.server_name
                or evidence["server_version"] != entry.approval.server.server_version
                or evidence["remote_tool"] != entry.approval.server.tool_name
                or evidence["schema_hash"] != entry.approval.server.schema_hash
                or evidence["endpoint_hash"] != evidence_hash(entry.approval.server.endpoint)
                or evidence["input_hash"] != invocation.input_hash):
            raise PermissionDeniedError("MCP result provenance differs from Core authority.")
        return data, evidence

    def summaries(self, context):
        self.core.permission_engine.enforce("run:read", context, context.organization_id, context.project_id)
        result = []
        for key, entry in list(self._entries.items()):
            if key[:2] != (context.organization_id, context.project_id):
                continue
            available = True
            try:
                self._valid(entry)
            except PermissionDeniedError:
                available = False
            spec = entry.approval.server
            result.append({"namespace": spec.capability, "adapter": "approved_loopback_mcp",
                "risk": "read", "available": available, "effective_permission": available and
                    self.core.permission_engine.evaluate("run:create", context, context.organization_id, context.project_id).allowed,
                "modes": ["local"], "requirements": ["exact published version binding", "active assignment",
                    "current human approval", "Core budget and deadline"],
                "missing_prerequisites": [] if available else ["fresh verified MCP approval"],
                "disabled_reason": None if available else "MCP approval unavailable"})
        return result
