"""Core-owned runtime observations and process-only gateway credential lifecycle.

Secrets use existing GatewaySettings, Core credential redaction and signed audits.
There is no credential database, secret manager, or native admin passthrough.
"""
import asyncio

from modules.core.errors import protect_diagnostic_logging, sanitize
from modules.core.permissions.engine import PermissionDeniedError
from packages.contracts.core import AuditStatus
from packages.model_adapters import GatewaySettings


class RuntimeControl:
    def __init__(self, core, *, local_administration=False, protect_credentials=None):
        self.core = core
        self.local_administration = local_administration
        self.protect_credentials = protect_credentials
        self._changes = asyncio.Lock()

    def authorize(self, context, action="run:read", *, session=None):
        self.core._fence()
        self.core.permission_engine.enforce(action, context, context.organization_id, context.project_id, session=session)

    async def inventory(self, context):
        self.authorize(context)
        inventory = await self.core.runtime_adapter.runtime_inventory()
        self.authorize(context)
        worker = self.core.mcp_tools.native_worker
        if worker is not None:
            discovered = []
            for toolset in inventory.toolsets:
                native = set(toolset.tools) & set(worker.schemas)
                discovered.append(toolset.model_copy(update={"execution_environment": "isolated_worker",
                    "configuration_readiness": "ready" if native == set(toolset.tools) else "unknown",
                    "risk": "execution" if native == set(toolset.tools) else "unknown",
                    "reason": "exact_core_action_approval_and_version_grants_required" if native == set(toolset.tools)
                        else "only_explicitly_approved_native_members_supported_other_members_unverified"})
                    if native else toolset)
            inventory = inventory.model_copy(update={"toolsets": discovered,
                "settings": {**inventory.settings, "native_worker_image": worker.image_id}})
        payload = {"organization_id": context.organization_id, "project_id": context.project_id,
            "inventory": inventory.model_dump(mode="json")}
        clean = sanitize(payload, credentials=getattr(self.core.db_manager, "protected_credentials", ()))
        if clean != payload:
            raise PermissionDeniedError("Runtime inventory contains protected metadata.")
        return {**payload, "attestation": self.core.db_manager.evidence_signer.sign("runtime_inventory", payload)}

    async def connection(self, context, *, refresh=False):
        self.authorize(context, "system:health")
        adapter = self.core.runtime_adapter
        gateway = getattr(adapter, "model_gateway", None)
        if gateway is None:
            return {"supported": False, "reason": "gateway_connection_api_unavailable"}
        revoked = getattr(adapter, "_gateway_revoked", False)
        if revoked:
            from packages.contracts.runtime import GatewayDiscovery
            discovery = GatewayDiscovery(reason="gateway_connection_revoked")
        else:
            discovery = await gateway.discover(refresh=refresh)
        binding = await adapter.capability_verification_binding()
        self.authorize(context, "system:health")
        return {"supported": True, "gateway": "9Router", "base_url": gateway.settings.base_url,
            "configuration_id": gateway.settings.configuration_id,
            "credential_configured": not revoked and bool(gateway.settings.api_key.get_secret_value()),
            "enabled": not revoked,
            "credential_storage": "trusted_process_memory", "persistent_credentials": False,
            "administration_available": self.local_administration,
            "connected": discovery.connected, "discovery_valid": discovery.discovery_valid,
            "runtime_binding_verified": binding is not None,
            "reason": discovery.reason, "models": discovery.models,
            "upstream_request_count": "unknown", "final_cost_verification": "unavailable"}

    async def change_connection(self, context, change, *, revoke=False):
        self.authorize(context, "tool:register")
        if not self.local_administration:
            raise PermissionDeniedError("Gateway administration requires tenant-isolated runtime binding and a trusted credential provider for hosted use.")
        adapter = self.core.runtime_adapter
        gateway = getattr(adapter, "model_gateway", None)
        if gateway is None or not hasattr(adapter, "replace_gateway_connection"):
            raise PermissionDeniedError("Runtime gateway lifecycle is unsupported.")
        replacement = GatewaySettings(base_url=gateway.settings.base_url, api_key="") if revoke else GatewaySettings(base_url=change.base_url, api_key=change.api_key)
        async with self._changes:
            self.core.db_manager._gateway_reconfiguration = True
            self.core.db_manager.engine._aryn_gateway_reconfiguration = True
            try:
                from database.schema import RunStateModel
                with self.core.db_manager.session(write=True) as session:
                    self.authorize(context, "tool:register", session=session)
                    if gateway.settings.configuration_id != change.expected_configuration_id:
                        raise PermissionDeniedError("Gateway configuration changed; reload before replacement.")
                    if session.query(RunStateModel).filter(RunStateModel.status.in_(
                            ["queued", "started", "running", "stopping", "outcome_unknown"])).first():
                        raise PermissionDeniedError("Settle all active or uncertain executions before replacing credentials.")
                secret = replacement.api_key.get_secret_value()
                protected = getattr(self.core.db_manager, "protected_credentials", ())
                if secret and secret not in protected:
                    if len(protected) >= 128:
                        raise PermissionDeniedError("Temporary credential protection capacity exceeded.")
                    self.core.db_manager.protected_credentials = (*protected, secret)
                if self.protect_credentials:
                    self.protect_credentials(secret)
                protect_diagnostic_logging((secret,))
                # Fail closed before I/O: a lost reply cannot leave old readiness usable.
                self.core.model_router.replace_catalog([])
                gateway.bind_runtime_configuration(None)
                gateway._tool_probes.clear()
                gateway._runtime_verified.clear()
                adapter._gateway_revoked = True
                await adapter.replace_gateway_connection(replacement, change.expected_configuration_id, revoke=revoke)
                self.authorize(context, "tool:register")
                self.core.audit_logger.record("core.gateway.revoked" if revoke else "core.gateway.replaced",
                    context, "9router", AuditStatus.COMPLETED,
                    {"previous_configuration_id": change.expected_configuration_id,
                        "configuration_id": replacement.configuration_id, "persistent_credentials": False})
            finally:
                self.core.db_manager._gateway_reconfiguration = False
                self.core.db_manager.engine._aryn_gateway_reconfiguration = False
        return await self.connection(context)
