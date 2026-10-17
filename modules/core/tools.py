"""Session-scoped tool approvals under existing Core identity, owner and audit.

No persisted secrets or automatic restoration: restart loses approvals and denies
old bindings. AgentVersion metadata authenticates the exact approval binding.
"""
from __future__ import annotations

import time
import uuid
import threading
import re
from dataclasses import dataclass

from pydantic import SecretStr

from modules.core.permissions.engine import PermissionDeniedError
from modules.core.errors import sanitize, protect_diagnostic_logging
from packages.contracts.bench import evidence_hash
from packages.contracts.core import AuditStatus
from packages.contracts.tool import MCPApproval, MCPInvocation, MCPResultEvidence, MCPServerDefinition, checked_data, loopback_endpoint
from packages.tool_adapters.mcp import MCPAdapter
from packages.contracts.tool import (HTTPSApproval, HTTPSConnectionDefinition, HTTPSInvocation, HTTPSResultEvidence,
    GitHubIssueConnectionDefinition, GitHubIssueResultEvidence, GITHUB_API_ORIGIN)
from packages.tool_adapters.https import HTTPSAdapter, HTTPSTrust
from packages.contracts.native_tool import NativeApproval, NativeToolDefinition


def clock():
    return time.time()


@dataclass
class ApprovedTool:
    approval: MCPApproval | HTTPSApproval | NativeApproval
    adapter: object
    owner_context: object

    @property
    def definition(self):
        return self.approval.connection if isinstance(self.approval, (HTTPSApproval, NativeApproval)) else self.approval.server

    @property
    def native(self):
        return isinstance(self.approval, NativeApproval)

    @property
    def https(self):
        return isinstance(self.approval, HTTPSApproval)

    @property
    def identifier(self):
        return self.definition.connection_id if self.https or self.native else self.definition.server_id

    @property
    def kind(self):
        if self.native:
            return "native"
        if isinstance(self.definition, GitHubIssueConnectionDefinition):
            return "github"
        return "https" if self.https else "mcp"

    @property
    def action(self):
        if self.native:
            return "native." + self.definition.tool_name
        return "github.issue.read" if self.kind == "github" else self.kind + ".read"


class CoreTools:
    def __init__(self, core, approved_endpoints=(), *, https_endpoints=(), https_trust=None):
        self.core = core
        self._endpoints = frozenset(loopback_endpoint(url) for url in approved_endpoints)
        self._entries = {}
        self._changes = threading.RLock()
        self._https_trust = https_trust if https_trust is not None else HTTPSTrust(https_endpoints)
        self.native_worker = None

    def register_native(self, context, review):
        from packages.contracts.tool import ToolDeclaration
        self._manage(context)
        worker = self.native_worker
        if worker is None or review.tool_name not in worker.schemas:
            raise PermissionDeniedError("A reviewed immutable native worker and its installed tool schema are required.")
        checked_data(review.arguments, worker.schemas[review.tool_name]["parameters"])
        if sanitize(review.arguments, credentials=getattr(self.core.db_manager, "protected_credentials", ())) != review.arguments:
            raise PermissionDeniedError("Native tool approval cannot contain protected credentials.")
        declaration = ToolDeclaration(name="aryn_native_" + review.tool_name,
            input_schema={"type": "object", "properties": {key: {"const": value} for key, value in review.arguments.items()},
                "required": sorted(review.arguments), "additionalProperties": False})
        spec = NativeToolDefinition(connection_id=review.connection_id, organization_id=context.organization_id,
            project_id=context.project_id, owner_id=context.actor.actor_id, tool_name=review.tool_name,
            declaration=declaration, arguments=review.arguments, image_id=worker.image_id)
        binding_id = uuid.uuid4().hex
        binding_hash = evidence_hash({"connection": spec.model_dump(mode="json"), "binding_id": binding_id})
        authority = self.core.db_manager.approval_authority
        if authority is None:
            raise PermissionDeniedError("Existing Core human approval authority is required.")
        key = (context.organization_id, context.project_id, declaration.name)
        with self._changes:
            if (key in self._entries or len(self._entries) >= 128 or any(
                    scope[:2] == key[:2] and entry.identifier == review.connection_id for scope, entry in self._entries.items())):
                raise PermissionDeniedError("Revoke the existing native action before replacement.")
            record = authority.grant_approval(context, "native_tool_binding", binding_id, binding_hash,
                comments="Exact sandboxed native action reviewed by the human operator.")
            observed = clock()
            approval = NativeApproval(connection=spec, binding_id=binding_id, binding_hash=binding_hash,
                approval_id=record.approval_id, observed_at=observed, expires_at=observed + review.ttl_seconds)
            approval = approval.model_copy(update={"attestation": self.core.db_manager.evidence_signer.sign("native_tool_binding", approval.payload())})
            self.core.audit_logger.record("core.native.registered", context, spec.connection_id, AuditStatus.ALLOWED,
                {"approval": approval.model_dump(mode="json"), "sandbox": worker.profile()})
            self._entries[key] = ApprovedTool(approval, worker, context.model_copy(deep=True))
        return approval.model_dump(mode="json")

    def _connection_identity(self, binding_id, secret):
        return evidence_hash(self.core.db_manager.evidence_signer.sign("mcp_connection",
            {"binding_id": binding_id, "secret": secret.get_secret_value()}))

    def _manage(self, context):
        self.core._fence()
        self.core.permission_engine.enforce("tool:register", context, context.organization_id, context.project_id)

    async def register(self, context, definition: MCPServerDefinition | HTTPSConnectionDefinition, secret: SecretStr, *, ttl_seconds=300):
        self._manage(context)
        https = isinstance(definition, HTTPSConnectionDefinition)
        github = isinstance(definition, GitHubIssueConnectionDefinition)
        contract = GitHubIssueConnectionDefinition if github else HTTPSConnectionDefinition if https else MCPServerDefinition
        spec = contract.model_validate_json(definition.model_dump_json())
        if github:
            self._https_trust.check_service_origin(spec.endpoint, GITHUB_API_ORIGIN)
        endpoints = self._https_trust.endpoints if https else self._endpoints
        if (spec.organization_id != context.organization_id or spec.project_id != context.project_id
                or spec.owner_id != context.actor.actor_id or spec.endpoint not in endpoints
                or spec.risk != "READ_ONLY" or not spec.enabled or type(ttl_seconds) is not int
                or not 1 <= ttl_seconds <= 300 or not isinstance(secret, SecretStr)
                or len(secret.get_secret_value()) < 32
                or https and (len(secret.get_secret_value()) > 256
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", secret.get_secret_value()))
                or sanitize(spec.model_dump(mode="json"), credentials=(secret.get_secret_value(),)) != spec.model_dump(mode="json")):
            raise PermissionDeniedError("Tool registration is outside the approved read-only scope.")
        key = (spec.organization_id, spec.project_id, spec.declaration.name)
        identifier = spec.connection_id if https else spec.server_id
        kind = "github" if github else "https" if https else "mcp"
        def collision():
            return key in self._entries or len(self._entries) >= 128 or any(
                entry.identifier == identifier
                and entry.definition.organization_id == spec.organization_id
                and entry.definition.project_id == spec.project_id for entry in self._entries.values())
        if collision():
            raise PermissionDeniedError("Tool identity is already registered; revoke before replacement.")
        binding = uuid.uuid4().hex
        connection_identity = self._connection_identity(binding, secret)
        observed_at = clock()
        if https:
            import asyncio
            async with asyncio.timeout(spec.timeout_seconds):
                addresses = await self._https_trust.resolve(spec.endpoint)
            approval = HTTPSApproval(connection=spec, binding_id=binding, connection_identity=connection_identity,
                binding_hash="0" * 64, addresses=addresses, trust_hash=self._https_trust.identity(),
                observed_at=observed_at, expires_at=observed_at + ttl_seconds)
            approval = approval.model_copy(update={"binding_hash": approval.configuration_hash()})
            adapter = HTTPSAdapter(approval, secret, self._https_trust)
        else:
            approval = MCPApproval(server=spec, binding_id=binding,
                connection_identity=connection_identity,
                binding_hash=evidence_hash({"server": spec.model_dump(mode="json"), "binding_id": binding,
                    "connection_identity": connection_identity}),
                observed_at=observed_at, expires_at=observed_at + ttl_seconds)
            adapter = MCPAdapter(approval, secret)
            await adapter.discover()
        approval_contract = HTTPSApproval if https else MCPApproval
        approval_kind = "https_connection_approval" if https else "mcp_server_approval"
        with self._changes:
            self._manage(context)
            if collision() or clock() >= approval.expires_at:
                raise PermissionDeniedError("Tool registration authority changed during verification.")
            approval = approval.model_copy(update={"attestation": self.core.db_manager.evidence_signer.sign(
                approval_kind, approval.payload())})
            adapter.approval = approval_contract.model_validate_json(approval.model_dump_json())
            if https:
                # Reuse existing diagnostics/audit protection. Never persist a secret.
                protected = getattr(self.core.db_manager, "protected_credentials", ())
                if secret.get_secret_value() not in protected:
                    if len(protected) >= 128:
                        raise PermissionDeniedError("Temporary credential protection capacity exceeded.")
                    self.core.db_manager.protected_credentials = (*protected, secret.get_secret_value())
                protect_diagnostic_logging((secret.get_secret_value(),))
            self.core.audit_logger.record("core." + kind + ".registered", context, identifier, AuditStatus.ALLOWED,
                {"binding_hash": approval.binding_hash, "schema_hash": spec.schema_hash,
                 "tool_name": spec.declaration.name, "risk": spec.risk,
                 **({"remote_tool": spec.tool_name, "protocol": approval.protocol} if not https else {}),
                 "endpoint_hash": evidence_hash(spec.endpoint),
                 "expires_at": approval.expires_at, "source": "https_transport" if https else "authenticated_loopback_mcp"})
            self._entries[key] = ApprovedTool(approval, adapter, context.model_copy(deep=True))
        return approval_contract.model_validate_json(approval.model_dump_json())

    def revoke(self, context, server_id):
        self._manage(context)
        with self._changes:
            key = next((key for key, value in self._entries.items()
                if key[:2] == (context.organization_id, context.project_id)
                and value.identifier == server_id), None)
            if key is None or self._entries[key].definition.owner_id != context.actor.actor_id:
                raise PermissionDeniedError("Tool registration unavailable in this scope.")
            entry = self._entries[key]
            self.core.audit_logger.record("core." + entry.kind + ".revoked", context, server_id, AuditStatus.COMPLETED,
                {"binding_hash": entry.approval.binding_hash})
            del self._entries[key]

    def _valid(self, entry):
        approval = entry.approval
        if entry.native:
            if (approval.configuration_hash() != approval.binding_hash or not approval.observed_at <= clock() < approval.expires_at
                    or approval.expires_at > approval.observed_at + 300 or entry.adapter is not self.native_worker
                    or entry.definition.image_id != entry.adapter.image_id
                    or not self.core.db_manager.evidence_signer.verify("native_tool_binding", approval.payload(), approval.attestation)):
                raise PermissionDeniedError("Native action approval is stale or differs from its isolated worker.")
            self.core.db_manager.approval_authority.verify_approval(entry.owner_context, "native_tool_binding",
                approval.binding_id, approval.binding_hash)
            self.core.permission_engine.enforce("tool:register", entry.owner_context,
                entry.definition.organization_id, entry.definition.project_id)
            return
        try:
            trust_matches = not entry.https or entry.adapter.trust.identity() == approval.trust_hash
        except (LookupError, ValueError):
            trust_matches = False
        if (not entry.definition.enabled or entry.definition.risk != "READ_ONLY"
                or not approval.observed_at <= clock() < approval.expires_at <= approval.observed_at + 300
                or clock() - approval.observed_at > 60
                or approval.configuration_hash() != approval.binding_hash
                or entry.adapter.approval != approval
                or not trust_matches
                or not entry.adapter.connection_matches(approval.connection_identity,
                    lambda secret: self._connection_identity(approval.binding_id, secret))
                or not self.core.db_manager.evidence_signer.verify(
                    "https_connection_approval" if entry.https else "mcp_server_approval", approval.payload(), approval.attestation)):
            raise PermissionDeniedError("Tool approval is expired, stale or unverified.")
        # Read the owner separately: avoid acquiring a second membership write
        # lock in inverse order to the run actor's existing Core claim lock.
        self.core.permission_engine.enforce("tool:register", entry.owner_context,
            entry.definition.organization_id, entry.definition.project_id)

    def current(self, context, name, binding_hash=None, *, session=None):
        self.core._fence()
        self.core.permission_engine.enforce("run:create", context,
            context.organization_id, context.project_id, session=session)
        entry = self._entries.get((context.organization_id, context.project_id, name))
        if entry is None or binding_hash is not None and entry.approval.binding_hash != binding_hash:
            raise PermissionDeniedError("Exact tool binding is unavailable.")
        self._valid(entry)
        return entry

    def pins(self, context, version, grants, *, session=None):
        from packages.tool_adapters.fixture import NAME
        names = set(grants) - {NAME}
        if not names:
            return {}
        mcp, https = version.metadata.get("mcp_bindings", {}), version.metadata.get("https_bindings", {})
        native = version.metadata.get("native_bindings", {})
        if (not isinstance(mcp, dict) or not isinstance(https, dict) or not isinstance(native, dict)
                or set(mcp) & set(https) or set(native) & (set(mcp) | set(https))):
            raise PermissionDeniedError("Tool binding metadata is invalid.")
        bindings = {**mcp, **https, **native}
        if (set(bindings) != set(version.tool_grants) - {NAME}
                or any(not name.startswith("aryn_mcp_") for name in mcp)
                or any(not name.startswith(("aryn_https_", "aryn_github_")) for name in https)
                or any(not name.startswith("aryn_native_") for name in native)
                or len(grants) > 32 or any(not isinstance(value, str) for value in bindings.values())
                or version.tool_policy.network_access or version.tool_policy.file_write_access
                or version.tool_policy.code_execution):
            raise PermissionDeniedError("Version must bind exact approved Core tools without host grants.")
        return {name: self.current(context, name, bindings.get(name), session=session).approval.binding_hash for name in names}

    async def invoke(self, context, call, execution_context, binding_hash, reauthorize):
        entry = self.current(context, call.name, binding_hash)
        if entry.native:
            checked_data(call.arguments, entry.definition.declaration.input_schema)
            payload = {**execution_context.model_dump(), "call_id": call.call_id, "binding_hash": binding_hash,
                "input_hash": evidence_hash(call.arguments), "sandbox": entry.adapter.profile(),
                "configuration_hash": evidence_hash(entry.definition.model_dump(mode="json"))}
            invocation = {"payload": payload, "attestation": self.core.db_manager.evidence_signer.sign("native_tool_call", payload)}
            self.core.audit_logger.record("core.native.admission", context, execution_context.run_id, AuditStatus.ALLOWED, invocation)
            data, evidence = await entry.adapter.invoke(entry.definition, call, execution_context, invocation,
                self.core.db_manager.evidence_signer.verify, reauthorize)
            expected = {"run_id": execution_context.run_id, "organization_id": context.organization_id,
                "project_id": context.project_id, "call_id": call.call_id, "input_hash": evidence_hash(call.arguments),
                "output_hash": evidence_hash(data), "invocation_hash": evidence_hash(invocation), "sandbox": entry.adapter.profile()}
            if (not isinstance(data, dict) or set(data) != {"text"} or not isinstance(data["text"], str)
                    or len(data["text"].encode()) > 16384 or not isinstance(evidence, dict)
                    or any(evidence.get(key) != value for key, value in expected.items())):
                raise PermissionDeniedError("Native tool execution evidence differs from signed Core admission.")
            if sanitize(data, credentials=getattr(self.core.db_manager, "protected_credentials", ())) != data:
                raise PermissionDeniedError("Native result contains protected credentials.")
            self.current(context, call.name, binding_hash)
            return data, expected
        if entry.https:
            return await self._invoke_https(entry, context, call, execution_context, binding_hash, reauthorize)
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

    async def _invoke_https(self, entry, context, call, execution_context, binding_hash, reauthorize):
        spec = entry.definition
        checked_data(call.arguments, spec.declaration.input_schema)
        invocation = HTTPSInvocation(**execution_context.model_dump(), call_id=call.call_id,
            trace_id=context.correlation_id, binding_hash=binding_hash, input_hash=evidence_hash(call.arguments))
        invocation = invocation.model_copy(update={"deadline_at": min(invocation.deadline_at, entry.approval.expires_at)})
        invocation = invocation.model_copy(update={"attestation": self.core.db_manager.evidence_signer.sign(
            "https_tool_call", invocation.payload())})
        data, evidence = await entry.adapter.invoke(call.arguments, invocation,
            self.core.db_manager.evidence_signer.verify, reauthorize)
        github = isinstance(spec, GitHubIssueConnectionDefinition)
        contract = GitHubIssueResultEvidence if github else HTTPSResultEvidence
        evidence = contract.model_validate(evidence).model_dump(mode="json")
        if not entry.adapter.consume_receipt(invocation, evidence):
            raise PermissionDeniedError("HTTPS transport receipt is unavailable or differs.")
        reauthorize()
        self.current(context, call.name, binding_hash)
        checked_data(data, spec.output_schema)
        expected = {"run_id": invocation.run_id, "trace_id": invocation.trace_id, "call_id": call.call_id,
            "organization_id": context.organization_id, "project_id": context.project_id,
            "connection_id": spec.connection_id, "tool_name": call.name, "binding_hash": binding_hash,
            "schema_hash": spec.schema_hash, "endpoint_hash": evidence_hash(spec.endpoint),
            "input_hash": invocation.input_hash, "output_hash": evidence_hash(data),
            "invocation_hash": evidence_hash(invocation.model_dump(mode="json")),
            "target_hash": evidence_hash({"endpoint": spec.endpoint, "addresses": entry.approval.addresses,
                "route": entry.adapter.request_route(call.arguments)})}
        if github:
            expected.update(connector_identity="github.issue.read", repository_binding_hash=spec.repository_binding_hash,
                issue_number=call.arguments["issue_number"])
        if (any(evidence[key] != value for key, value in expected.items())
                or sanitize(data, credentials=getattr(self.core.db_manager, "protected_credentials", ())) != data):
            raise PermissionDeniedError("HTTPS result provenance differs from Core authority.")
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
            spec = entry.definition
            result.append({"namespace": spec.capability, "adapter": "isolated_native_hermes" if entry.native else "approved_pinned_https" if entry.https else "approved_loopback_mcp",
                "risk": "privileged" if entry.native else "read", "available": available, "effective_permission": available and
                    self.core.permission_engine.evaluate("run:create", context, context.organization_id, context.project_id).allowed,
                "modes": ["local", "hosted"] if entry.https else ["local"], "requirements": ["exact published version binding", "active assignment",
                    "current human approval", "Core budget and deadline"],
                "missing_prerequisites": [] if available else ["fresh verified tool approval"],
                "disabled_reason": None if available else "Tool approval unavailable"})
        return result


# Compatibility for existing MCP composition/tests: the same registry and owner.
MCPTools = CoreTools
