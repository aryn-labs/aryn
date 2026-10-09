"""Studio authentication boundary; all authorization belongs to ARYN Core."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from database.connection import DatabaseManager, create_db_engine
from database.repositories.agent_repo import AgentRepository
from database.repositories.agent_activation_repo import AgentActivationRepository
from database.repositories.bench_repo import BenchRepository
from database.repositories.bench_regression_repo import BenchRegressionRepository, RegressionGateFailedError
from database.repositories.budget_repo import BudgetRepository
from database.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    TenantIsolationError,
)
from database.repositories.organization_repo import OrganizationRepository
from database.schema import (
    AgentBlueprintModel,
    AgentVersionModel,
    AgentAssignmentModel,
    ApprovalModel,
    AuditEventModel,
    BenchEvaluationModel,
    OrganizationModel,
    ProjectModel,
    RunStateModel,
)
from modules.agent_factory.service import AgentFactoryService, ForbiddenToolError
from modules.agent_factory.editor import AgentEditor, EditorConflictError
from packages.contracts.agent_builder import WorkingCopyInput, WorkingCopyView, GenerationInput, LayoutInput, LayoutView, LifecycleProjection, StopInput, StopReceipt
from modules.bench.quality_gate import QualityGateFailedError
from modules.bench.runner import BenchRunner
from modules.bench.scenarios import get_bench_suite_registry
from modules.core.approvals.engine import (
    ApprovalRequiredError,
    PayloadHashMismatchError,
    UnauthorizedApproverError,
)
from modules.core.audit.logger import AuditLogger
from modules.core.identity.binder import TrustedIdentityBinder
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.usage.engine import BudgetExceededError
from modules.core.workflows.coordinator import (
    IdempotencyConflictError,
    RunCoordinator,
    RunInProgressError,
)
from packages.contracts.agent import AgentVersion, VersionIntegrityError, RollbackIntent
from packages.contracts.core import AuditStatus
from packages.contracts.runtime import (ModelUnavailableError, GatewayUnavailableError, ModelIdentityError, RuntimeGatewayError)
from packages.contracts.model import ModelProviderType, ModelSpec
from packages.contracts.workspace import DivisionInput, DivisionUpdate, ResourceItem, ResourcePage, WorkspaceSummary
from modules.core.workspace import WorkspaceService
from services.api.workspace_reads import WorkspaceReads
from packages.model_adapters import ModelRouter, ModelRoutingError
from packages.runtime_adapters import HermesAdapterError, HermesRuntimeAdapter, RuntimeAuthenticationError
from services.api.authentication import (
    AuthenticationSettings, HostedAuthentication, HOSTED_COOKIE, Principal, principal_context,
)

ROOT = Path(__file__).resolve().parents[2]
DEV_ORG = "org_studio_local"
DEV_ACTOR = "studio_local_owner"
DEV_PROJECT = "proj_studio_research"
COOKIE = "aryn_studio_session"
SESSION_TTL = 8 * 3600


class BlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(
        min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str = Field(default="", max_length=2000)
    role: Optional[str] = Field(default=None, max_length=64)
    objective: Optional[str] = Field(default=None, max_length=2000)
    owner: Optional[str] = Field(default=None, max_length=64)


class BaselineAcceptanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    evaluation_id: str = Field(min_length=1, max_length=64)
    expected_baseline_id: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(min_length=3, max_length=2000)
    suite_transition: bool = False


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version_number: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$",
    )
    system_prompt: str = Field(min_length=20, max_length=12000)
    model: str = Field(min_length=1, max_length=128)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=128, le=4096)
    tool_grants: list[str] = Field(default_factory=list, max_length=0)
    schema_version: Optional[str] = Field(default="1.0.0", max_length=32)
    role: Optional[str] = Field(default=None, max_length=64)
    objective: Optional[str] = Field(default=None, max_length=4000)
    owner: Optional[str] = Field(default=None, max_length=64)
    output_contract: Optional[dict[str, Any]] = None
    constraints: Optional[dict[str, Any] | list[str]] = None
    tool_policy: Optional[dict[str, Any]] = None
    model_policy: Optional[dict[str, Any]] = None
    budget_policy: Optional[dict[str, Any]] = None
    evaluation_reference: Optional[dict[str, Any]] = None


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    comments: str = Field(min_length=5, max_length=2000)
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    blueprint_id: str = Field(min_length=1, max_length=64)
    version_id: str = Field(min_length=1, max_length=64)
    role_name: str = Field(min_length=2, max_length=64)


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    assignment_id: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=5, max_length=12000)
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,100}$")
    allow_remote_model: bool = False


class StudioHermesAdapter(HermesRuntimeAdapter):
    """Text-only boundary for evaluation and execution; zero live write tools."""

    async def execute_direct_turn(self, request, context):
        caps = await self.capabilities()
        if caps.enabled_toolsets:
            raise PermissionDeniedError("Studio requires all Hermes toolsets disabled.")
        result = await super().execute_direct_turn(request, context)
        if result.model != request.model:
            raise ModelRoutingError(
                "Runtime reported a different model; silent fallback is forbidden."
            )
        return result


def runtime_key() -> str:
    """Runtime authentication only, explicitly supplied to the server process."""
    from packages.config import get_settings
    return get_settings().api_server_key.get_secret_value()


def row(model):
    data = {c.name: getattr(model, c.name) for c in model.__table__.columns}
    for name in list(data):
        value = data[name]
        if hasattr(value, "isoformat"):
            data[name] = value.isoformat() + ("Z" if value.tzinfo is None else "")
        if name.endswith("_json"):
            try:
                data[name.removesuffix("_json")] = json.loads(data.pop(name) or "{}")
            except (ValueError, TypeError):
                data[name.removesuffix("_json")] = None
                data["storage_valid"] = False
    return data


def migrate(engine):
    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def create_app(
    db: DatabaseManager | None = None,
    runtime=None,
    origin: str | None = None,
    testing=False,
    authentication: AuthenticationSettings | None = None,
    identity_provider=None,
):
    from packages.config import get_settings
    settings = get_settings()
    auth_config = authentication or AuthenticationSettings.from_env(settings)
    if auth_config.environment != settings.aryn_env or (settings.aryn_env != "development" and auth_config.mode != "oidc"):
        raise ValueError("Authentication mode must match the deployment environment.")
    local_development = auth_config.mode == "local-development"
    if not local_development:
        if origin is not None and origin != auth_config.public_origin:
            raise ValueError("Hosted origin must match the authenticated public origin.")
        origin = auth_config.public_origin
    if origin is None:
        origin = settings.studio_origin

    parsed_origin = urlsplit(origin)
    origin_host = (parsed_origin.hostname or "").lower()
    origin_port = parsed_origin.port
    if local_development and (
        parsed_origin.scheme != "http"
        or origin_host not in {"127.0.0.1", "localhost", "::1"}
        or origin_port is None
        or not (1024 <= origin_port <= 65535)
        or parsed_origin.username
        or parsed_origin.password
        or parsed_origin.query
        or parsed_origin.fragment
        or (parsed_origin.path and parsed_origin.path != "/")
    ):
        raise ValueError("Studio origin must be an explicit loopback port.")
    if db is None:
        if local_development:
            path = ROOT / ".local/studio.sqlite3"
            path.parent.mkdir(exist_ok=True)
            engine = create_db_engine(f"sqlite:///{path.as_posix()}")
        else:
            import os
            hosted_database_url = os.getenv("ARYN_DATABASE_URL", "")
            if not all((hosted_database_url, os.getenv("ARYN_EVIDENCE_SECRET", ""), os.getenv("ARYN_HISTORY_COMMITMENT_PATH", ""))):
                raise ValueError("Hosted database, evidence secret and protected history path must be explicit.")
            if len(runtime_key()) < 32:
                raise ValueError("Hosted runtime authentication requires an explicit strong key.")
            engine = create_db_engine(hosted_database_url)
        from modules.core.workflows.ownership import ExecutionAuthority
        ExecutionAuthority.for_engine(engine)
        migrate(engine)
        db = DatabaseManager(engine=engine)
    binder = TrustedIdentityBinder(secret_key=secrets.token_bytes(32) if local_development else auth_config.identity_secret.get_secret_value())
    permissions = PermissionEngine(db_manager=db, identity_binder=binder)
    audit = AuditLogger(db_manager=db)
    adapter = runtime or StudioHermesAdapter(base_url=settings.runtime_base_url, api_key=runtime_key(), timeout=10)
    protected_credentials = [
        auth_config.session_secret.get_secret_value(), auth_config.identity_secret.get_secret_value(),
        auth_config.client_secret.get_secret_value(),
        getattr(adapter, "api_key", ""),
        runtime_key(),
        settings.nine_router_api_key.get_secret_value(),
        settings.api_server_key.get_secret_value(),
    ]
    gateway_client = getattr(adapter, "model_gateway", None)
    if gateway_client and hasattr(gateway_client, "settings"):
        protected_credentials.append(gateway_client.settings.api_key.get_secret_value())
    db.protected_credentials = tuple(key for key in protected_credentials if key)
    from modules.core.errors import protect_diagnostic_logging
    protect_diagnostic_logging(db.protected_credentials)
    model_router = ModelRouter(catalog={})
    factory = AgentFactoryService(
        db, BenchRunner(adapter), permission_engine=permissions, audit_logger=audit, model_router=model_router
    )
    coordinator = RunCoordinator(
        adapter, permission_engine=permissions, audit_logger=audit, db_manager=db, model_router=model_router
    )
    workspace_reads = WorkspaceReads(db, permissions, coordinator)
    workspace_service = WorkspaceService(db, permissions)
    editor = AgentEditor(factory)
    sessions = {}
    mutation_lock = asyncio.Lock()
    # Provision only dedicated development scope. Do not re-grant a revoked membership on restart.
    with db.session() as s:
        repo = OrganizationRepository(s)
        if local_development and not s.get(OrganizationModel, DEV_ORG):
            repo.create_organization(DEV_ORG, "ARYN Lokal", "aryn-studio-local")
            repo.add_member(DEV_ORG, DEV_ACTOR, role="admin")
            ctx = binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
            repo.create_project(
                ctx, DEV_PROJECT, "Laboratorium Riset", "laboratorium-riset"
            )
            BudgetRepository(s).get_or_create_budget(ctx)

    coordinator.recover_in_flight_runs()
    with db.session(write=True) as s:
        interrupted_query = (
            s.query(AgentVersionModel)
            .join(AgentBlueprintModel)
            .filter(
                AgentVersionModel.status == "evaluating",
            )
        )
        if local_development:
            interrupted_query = interrupted_query.filter(AgentBlueprintModel.organization_id == DEV_ORG)
        interrupted = interrupted_query.all()
        for version in interrupted:
            if version.evaluation_owner_id == coordinator.authority.owner_id:
                continue
            version.status = "rejected"
            from packages.contracts.core import ActorType
            interrupted_ctx = binder.create_trusted_context(
                DEV_ACTOR if local_development else "core_execution_recovery", version.blueprint.organization_id,
                version.blueprint.project_id, actor_type=ActorType.USER if local_development else ActorType.SYSTEM)
            audit.record(
                "bench.evaluation.interrupted",
                interrupted_ctx,
                version.id,
                AuditStatus.FAILED,
                {
                    "reason": "Evaluasi terhenti saat layanan dimulai ulang. Jalankan Bench kembali."
                },
                session=s,
            )

    app = FastAPI(
        title="ARYN Studio — API lokal", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.db = db
    app.state.factory = factory
    app.state.binder = binder
    app.state.coordinator = coordinator
    app.state.sessions = sessions
    app.state.workspace_reads = workspace_reads
    app.state.workspace_service = workspace_service
    hosted = None if local_development else HostedAuthentication(db, auth_config, identity_provider)
    app.state.authentication = hosted
    app.state.authentication_settings = auth_config
    if hosted:
        hosted.mount(app)

    from contextvars import ContextVar
    request_correlation = ContextVar("studio_correlation", default=None)

    def fail(code, message, run_id=None):
        return JSONResponse({"message": message, "error_code": f"http_{code}", "correlation_id": request_correlation.get(), "run_id": run_id}, status_code=code)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.correlation_id = secrets.token_hex(16)
        request_correlation.set(request.state.correlation_id)
        principal_context.set(None)
        if local_development:
            if (request.client is None or request.client.host not in {"127.0.0.1", "::1"}
                    or any(name == "forwarded" or name.startswith("x-forwarded-") for name in request.headers)):
                return fail(403, "Studio development hanya dapat diakses melalui loopback langsung.")
            if request.headers.get("host") != parsed_origin.netloc:
                return fail(403, "Host tidak diizinkan. Gunakan alamat loopback Studio.")
        else:
            try:
                auth_config.check_request(request)
            except HTTPException as exc:
                return fail(exc.status_code, "Boundary HTTPS/host/proxy tidak valid.")
        if request.url.path.startswith(("/docs", "/redoc", "/openapi", "/debug", "/diagnostics")):
            return fail(404, "Endpoint tidak tersedia.")
        is_api = request.url.path.startswith("/api/")
        if is_api:
            credential_input = request.url.path + request.url.query
            if request.method not in {"GET", "HEAD"}:
                body = await request.body()
                if len(body) > 65536:
                    return fail(413, "Isi permintaan terlalu besar.")
                credential_input += body.decode("utf-8", errors="replace")
                try:
                    credential_input += json.dumps(json.loads(body), ensure_ascii=False)
                except ValueError:
                    pass
            if any(key and key in credential_input for key in protected_credentials):
                return fail(422, "Credential server tidak boleh disertakan dalam data aplikasi.")
            supplied_origin = request.headers.get("origin")
            if supplied_origin and supplied_origin != origin:
                return fail(403, "Origin permintaan tidak diizinkan.")
            if request.method not in {"GET", "HEAD"}:
                if (
                    supplied_origin != origin
                    or request.headers.get("sec-fetch-site", "same-origin")
                    != "same-origin"
                ):
                    return fail(403, "Mutasi harus berasal dari origin Studio yang dikonfigurasi.")
                if len(await request.body()) > 65536:
                    return fail(413, "Isi permintaan terlalu besar.")
            if hosted:
                try:
                    principal_context.set(hosted.principal(request))
                except HTTPException:
                    return JSONResponse({"message": "Autentikasi diperlukan.", "error_code": "authentication_required", "login_url": "/auth/login"}, status_code=401,
                        headers={"Cache-Control": "no-store"})
                if request.url.path != "/api/session" and request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
                        request.headers.get("x-csrf-token", "").encode(), hosted.csrf(request.cookies.get(HOSTED_COOKIE, "")).encode()):
                    return fail(403, "Token keamanan sesi tidak valid.")
            elif request.url.path != "/api/session":
                session = sessions.get(request.cookies.get(COOKIE, ""))
                if not session or session["expires"] < time.time():
                    return fail(401, "Sesi development berakhir. Muat ulang Studio.")
                if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
                    request.headers.get("x-csrf-token", "").encode(), session["csrf"].encode()
                ):
                    return fail(
                        403, "Token keamanan sesi tidak valid. Muat ulang Studio."
                    )
        try:
            if (
                is_api
                and request.method not in {"GET", "HEAD"}
                and request.url.path != "/api/session"
            ):
                async with mutation_lock:
                    response = await call_next(request)
            else:
                response = await call_next(request)
        except Exception as exc:
            from modules.core.errors import public_error
            response = JSONResponse(status_code=500, content=public_error(exc, correlation_id=request.state.correlation_id))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault("Content-Security-Policy", (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        ))
        if is_api:
            response.headers["Cache-Control"] = "no-store"
        if hosted:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.endswith("/working-copy"):
            from packages.contracts.agent_builder import AgentDraft
            allowed = set(AgentDraft.model_fields) | {"definition", "source_version_id", "expected_generation"}
            for policy in ("output_contract", "constraints", "tool_policy", "model_policy", "budget_policy", "evaluation_reference"):
                allowed.update(AgentDraft.model_fields[policy].annotation.model_fields)
            errors = [{"field": ".".join(str(part) if isinstance(part, int) or part in allowed else "field" for part in error["loc"] if part != "body"),
                "message": "Nilai field tidak sesuai kontrak."} for error in exc.errors()[:32]]
            return JSONResponse({"message": "Periksa konfigurasi AgentBuilder: format, panjang, atau nilai field belum sesuai.",
                "error_code": "editor_validation", "field_errors": errors, "correlation_id": request_correlation.get()}, status_code=422)
        return fail(
            422,
            "Periksa formulir: format, panjang, atau nilai belum sesuai. Klaim identitas dari browser tidak diterima.",
        )

    exception_map = {
        EditorConflictError: (409, "Generation working copy atau layout berubah. Muat ulang, lalu pulihkan input lokal sebelum menyimpan kembali."),
        RunInProgressError: (409, "Permintaan sudah tercatat. Periksa status dan riwayat; model tidak dijalankan ulang."),
        IdempotencyConflictError: (409, "Kunci permintaan sudah terikat pada input atau konfigurasi berbeda."),
        VersionIntegrityError: (
            409,
            "Integritas konfigurasi versi tidak valid atau memakai hash lama. Buat versi baru, jalankan Bench, dan setujui kembali.",
        ),
        PermissionDeniedError: (
            403,
            "Akses ditolak oleh Core. Periksa keanggotaan proyek, peran, dan batas tool runtime.",
        ),
        TenantIsolationError: (
            403,
            "Sumber daya berada di luar lingkup proyek yang diizinkan.",
        ),
        EntityNotFoundError: (404, "Sumber daya tidak ditemukan di proyek ini."),
        DuplicateEntityError: (
            409,
            "Nama unik, nomor versi, atau peran penugasan sudah digunakan.",
        ),
        IntegrityError: (
            409,
            "Data berbenturan dengan konfigurasi yang sudah tersimpan.",
        ),
        InvalidStateTransitionError: (
            409,
            "Tahap ini belum diizinkan. Periksa status versi dan persyaratan sebelumnya.",
        ),
        QualityGateFailedError: (
            409,
            "Bench terakhir belum lulus atau bukti evaluasi tidak cocok dengan versi ini.",
        ),
        ApprovalRequiredError: (
            409,
            "Publikasi memerlukan persetujuan yang cocok dengan hash konfigurasi.",
        ),
        PayloadHashMismatchError: (
            409,
            "Hash konfigurasi berbeda dari persetujuan. Evaluasi dan setujui versi kembali.",
        ),
        UnauthorizedApproverError: (
            403,
            "Persetujuan hanya dapat diberikan oleh pemilik development dengan peran admin aktif.",
        ),
        BudgetExceededError: (
            403,
            "Batas token proyek tidak mencukupi untuk permintaan ini.",
        ),
        ForbiddenToolError: (403, "Tool akses host tidak diizinkan di Studio."),
        ModelRoutingError: (
            409,
            "Model tidak diizinkan atau runtime melaporkan model berbeda. Tidak ada fallback otomatis.",
        ),
        HermesAdapterError: (
            503,
            "ARYN Runtime belum dapat menyelesaikan permintaan. Periksa koneksi, kredensial server, dan batas tool.",
        ),
        RuntimeError: (
            502,
            "Runtime tidak menyelesaikan eksekusi. Kegagalan dicatat oleh Core; periksa riwayat sebelum mencoba kembali.",
        ),
    }
    for error_type, (code, message) in exception_map.items():

        async def handler(request, exc, code=code, message=message):
            return fail(code, message, getattr(exc, "run_id", None))

        app.add_exception_handler(error_type, handler)

    @app.exception_handler(ModelUnavailableError)
    async def unavailable_model(request, exc):
        return fail(409 if exc.availability == "unavailable" else 503, "Model tidak tersedia melalui Model Gateway." if exc.availability == "unavailable" else "Ketersediaan model belum dapat diverifikasi.")

    @app.exception_handler(RegressionGateFailedError)
    async def regression_blocked(request, exc):
        return JSONResponse(status_code=409, content={"error_code": "regression_gate_failed", "message": "Promotion diblokir oleh regression gate.",
            "comparison": exc.comparison.model_dump(mode="json")})

    for gateway_error in (GatewayUnavailableError, RuntimeGatewayError, ModelIdentityError):
        async def gateway_handler(request, exc):
            return fail(409 if isinstance(exc, ModelIdentityError) else 503, "Bukti routing atau identitas model belum valid. Eksekusi ditolak.")
        app.add_exception_handler(gateway_error, gateway_handler)

    def context(project_id, action="run:read"):
        principal = principal_context.get() if hosted else Principal(DEV_ACTOR, DEV_ORG)
        if principal is None:
            raise HTTPException(401)
        ctx = binder.create_trusted_context(principal.actor_id, principal.organization_id, project_id,
            correlation_id=request_correlation.get(), auth_session_id=principal.session_id)
        try:
            permissions.enforce(action, ctx, ctx.organization_id, project_id)
        except PermissionDeniedError:
            audit.record(
                "studio.permission.denied",
                ctx,
                project_id,
                AuditStatus.DENIED,
                {"action": action},
            )
            raise
        return ctx

    async def runtime_status():
        health = None
        try:
            health = await adapter.health()
            caps = await adapter.capabilities()
            ready = (
                health.is_healthy and caps.tools_confined and not caps.enabled_toolsets
            )
            return {
                "connected": health.is_healthy,
                "ready": ready,
                "version": health.version,
                "tools_confined": caps.tools_confined,
                "enabled_toolsets": caps.enabled_toolsets,
                "message": "ARYN Runtime siap · tanpa tool"
                if ready
                else "Runtime dibatasi: seluruh toolset harus dinonaktifkan.",
                "readiness": health.details.get("status", "unknown"),
            }
        except RuntimeAuthenticationError:
            configured = bool(getattr(adapter, "api_key", ""))
            return {
                "connected": bool(health and health.is_healthy),
                "ready": False,
                "reason": "runtime_authentication_rejected" if configured else "runtime_authentication_missing",
                "message": "Autentikasi ARYN Runtime tidak cocok. Mulai ulang runtime dan Studio bersama."
                if configured else "Autentikasi ARYN Runtime belum dikonfigurasi. Jalankan runtime dan Studio bersama melalui start-aryn.ps1.",
            }
        except Exception:
            return {
                "connected": False,
                "ready": False,
                "message": "ARYN Runtime belum siap.",
            }

    async def require_runtime():
        if not (await runtime_status())["ready"]:
            raise HTTPException(
                503,
                "ARYN Runtime belum siap. Seluruh toolset harus dinonaktifkan dan autentikasi runtime harus valid.",
            )

    async def model_catalog():
        discovery = await adapter.discover_models(refresh=True)
        model_router.replace_catalog([ModelSpec(provider=ModelProviderType.NINE_ROUTER,
            model_id=m["model_id"], display_name=m["display_name"], requires_api_key=False)
            for m in discovery.models] if discovery.discovery_valid else [])
        return discovery

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return fail(exc.status_code, "Permintaan ditolak oleh kebijakan API Studio.")

    @app.post("/api/session")
    async def local_session(request: Request):
        # No roles, tokens, actor IDs, or identity input from the browser.
        if (await request.body()) not in {b"", b"{}"}:
            raise HTTPException(
                422, "Sesi development diterbitkan server tanpa input identitas."
            )
        if hosted:
            return {"csrf": hosted.csrf(request.cookies.get(HOSTED_COOKIE, "")), "mode": "oidc"}
        for key in list(sessions):
            if sessions[key]["expires"] < time.time():
                sessions.pop(key)
        sid = request.cookies.get(COOKIE, "")
        if sid not in sessions:
            if len(sessions) >= 32:
                raise HTTPException(
                    429,
                    "Batas sesi lokal tercapai. Mulai ulang layanan untuk membersihkan sesi.",
                )
            sid = secrets.token_urlsafe(32)
            sessions[sid] = {
                "csrf": secrets.token_urlsafe(32),
                "expires": time.time() + SESSION_TTL,
            }
        response = JSONResponse({"csrf": sessions[sid]["csrf"], "mode": "development"})
        response.set_cookie(
            COOKIE,
            sid,
            httponly=True,
            samesite="strict",
            max_age=SESSION_TTL,
            path="/api",
        )
        return response

    @app.get("/api/workspace/context")
    async def workspace_context():
        principal = principal_context.get() if hosted else Principal(DEV_ACTOR, DEV_ORG)
        if principal is None:
            raise HTTPException(401)
        ctx = binder.create_trusted_context(principal.actor_id, principal.organization_id, "", auth_session_id=principal.session_id)
        with db.session() as s:
            workspace_reads.authorize(s, ctx)
            projects = workspace_reads.query(s, ctx, "projects").order_by(ProjectModel.name, ProjectModel.id).limit(100).all()
            member = OrganizationRepository(s).get_member(principal.organization_id, principal.actor_id)
            organization = s.get(OrganizationModel, principal.organization_id)
            workspace_reads.authorize(s, ctx)
            return {"organization": {"id": organization.id, "name": organization.name},
                "projects": [{"id": p.id, "name": p.name} for p in projects],
                "user": {"id": principal.actor_id, "name": "Pemilik development" if local_development else principal.actor_id, "role": member.role},
                "mode": "isolated-test" if testing else "development" if local_development else "hosted",
                "models": [], "runtime": {"connected": False, "ready": False, "message": "Ketersediaan runtime belum diperiksa"},
                "gateway": {"name": "9Router", "connected": False, "discovery_valid": False, "runtime_binding_verified": False, "reason": "unmeasured"}}

    @app.get("/api/workspace")
    async def workspace():
        principal = principal_context.get() if hosted else Principal(DEV_ACTOR, DEV_ORG)
        if principal is None:
            raise HTTPException(401)
        with db.session() as s:
            from database.schema import ProjectModel
            accessible = []
            for project in s.query(ProjectModel).filter_by(organization_id=principal.organization_id).all():
                candidate = binder.create_trusted_context(principal.actor_id, principal.organization_id, project.id,
                    auth_session_id=principal.session_id)
                if permissions.evaluate("run:read", candidate, principal.organization_id, project.id, session=s).allowed:
                    accessible.append(project.id)
        if not accessible:
            raise PermissionDeniedError("No accessible projects.")
        ctx = context(accessible[0])
        discovery = await model_catalog()
        binding = await adapter.gateway_binding()
        context(accessible[0])  # Revalidate after asynchronous provider discovery.
        with db.session() as s:
            repo = OrganizationRepository(s)
            projects = [
                row(p)
                for p in repo.list_projects(ctx)
                if permissions.evaluate(
                    "run:read",
                    binder.create_trusted_context(principal.actor_id, principal.organization_id, p.id, auth_session_id=principal.session_id),
                    principal.organization_id,
                    p.id,
                ).allowed
            ]
            member = repo.get_member(principal.organization_id, principal.actor_id)
            role = member.role
            organization = s.get(OrganizationModel, principal.organization_id)
            organization_name = organization.name
        runtime = await runtime_status()
        context(accessible[0])
        return {
            "organization": {"id": principal.organization_id, "name": organization_name},
            "projects": projects,
            "user": {"name": "Pemilik development" if local_development else principal.actor_id, "id": principal.actor_id, "role": role},
            "models": discovery.models,
            "gateway": {"name": "9Router", "connected": discovery.connected,
                        "discovery_valid": discovery.discovery_valid, "reason": discovery.reason,
                        "runtime_binding_verified": binding},
            "runtime": runtime,
            "mode": "isolated-test" if testing else "development" if local_development else "hosted",
        }

    @app.get("/api/workspace/status")
    async def workspace_status():
        ctx = context("")
        discovery = await model_catalog()
        binding = await adapter.gateway_binding()
        runtime = await runtime_status()
        context("")
        return {"organization_id": ctx.organization_id, "models": discovery.models,
            "gateway": {"name": "9Router", "connected": discovery.connected, "discovery_valid": discovery.discovery_valid,
                "reason": discovery.reason, "runtime_binding_verified": binding}, "runtime": runtime}

    @app.get("/api/projects/{project_id}/summary", response_model=WorkspaceSummary)
    async def summary(project_id: str):
        return workspace_reads.summary(context(project_id))

    @app.get("/api/projects/{project_id}/resources/{resource}", response_model=ResourcePage[ResourceItem])
    async def resource_list(project_id: str, resource: str, request: Request,
        limit: int = Query(default=25, ge=1, le=100), cursor: str | None = Query(default=None, max_length=4096),
        q: str = Query(default="", max_length=100), status: str = Query(default="", max_length=32),
        sort: str = Query(default="newest", max_length=16), actor: str = Query(default="", max_length=64),
        resource_id: str = Query(default="", max_length=128), blueprint_id: str = Query(default="", max_length=64)):
        allowed = {"limit", "cursor", "q", "status", "sort", "actor", "resource_id", "blueprint_id"}
        if set(request.query_params) - allowed or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise HTTPException(422, "Unsupported query parameters.")
        return workspace_reads.page(context(project_id), resource, limit=limit, cursor=cursor, q=q,
            status=status, sort=sort, actor=actor, resource_id=resource_id, blueprint_id=blueprint_id)

    @app.get("/api/projects/{project_id}/resources/{resource}/{identifier}", response_model=ResourceItem)
    async def resource_detail(project_id: str, resource: str, identifier: str):
        return workspace_reads.detail(context(project_id), resource, identifier)

    @app.post("/api/projects/{project_id}/divisions", status_code=201)
    async def create_division(project_id: str, body: DivisionInput):
        from modules.core.errors import sanitize
        return sanitize(workspace_service.save_division(context(project_id, "division:manage"), body), credentials=protected_credentials)

    @app.post("/api/projects/{project_id}/divisions/{division_id}")
    async def update_division(project_id: str, division_id: str, body: DivisionUpdate):
        from modules.core.errors import sanitize
        return sanitize(workspace_service.save_division(context(project_id, "division:manage"), body, division_id), credentials=protected_credentials)

    @app.get("/api/projects/{project_id}/snapshot")
    async def snapshot(project_id: str):
        return await project_projection(project_id)

    @app.get("/api/projects/{project_id}/lifecycle", response_model=LifecycleProjection)
    async def lifecycle(project_id: str, request: Request, limit: int = Query(default=25, ge=1, le=50),
        blueprint_id: str = Query(default="", max_length=64), version_id: str = Query(default="", max_length=64),
        run_id: str = Query(default="", max_length=64), assignment_id: str = Query(default="", max_length=64),
        evaluation_id: str = Query(default="", max_length=64)):
        allowed = {"limit", "blueprint_id", "version_id", "run_id", "assignment_id", "evaluation_id"}
        if set(request.query_params) - allowed or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise HTTPException(422, "Unsupported lifecycle parameters.")
        return await project_projection(project_id, limit, blueprint_id, version_id, run_id, assignment_id, evaluation_id)

    async def project_projection(project_id, limit=None, blueprint_id="", version_id="", run_id="", assignment_id="", evaluation_id=""):
        ctx = context(project_id)
        with db.session() as s:
            repo = AgentRepository(s)
            captured_version = None
            if run_id:
                captured = s.query(RunStateModel).filter_by(id=run_id, organization_id=ctx.organization_id, project_id=project_id).first()
                if not captured or captured.execution_mode == "bench":
                    raise EntityNotFoundError("Run unavailable in this project.")
                captured_version, assignment_id = captured.agent_version_id, captured.assignment_id or ""
                version_id, blueprint_id, evaluation_id = captured_version or "", "", ""
            if evaluation_id:
                evaluation = BenchRepository(s, db.evidence_signer).get_evaluation(ctx, evaluation_id)
                version_id = evaluation.version_id
            if version_id:
                selected_version = repo.get_version(ctx, version_id)
                if blueprint_id and selected_version.blueprint_id != blueprint_id:
                    raise EntityNotFoundError("Version unavailable for this blueprint.")
                blueprint_id = selected_version.blueprint_id
            if blueprint_id:
                repo.get_blueprint(ctx, blueprint_id)
            assignments_query = s.query(AgentAssignmentModel).filter_by(organization_id=ctx.organization_id, project_id=project_id)
            if blueprint_id:
                assignments_query = assignments_query.filter_by(blueprint_id=blueprint_id)
            if assignment_id:
                repo.get_assignment(ctx, assignment_id)
                assignments_query = assignments_query.filter_by(id=assignment_id)
            assignments_query = assignments_query.order_by(AgentAssignmentModel.created_at.desc(), AgentAssignmentModel.id.desc())
            assignments = assignments_query.limit(limit).all() if limit else assignments_query.all()
            versions_query = (s.query(AgentVersionModel)
                .join(AgentBlueprintModel)
                .filter(
                    AgentBlueprintModel.organization_id == ctx.organization_id,
                    AgentBlueprintModel.project_id == project_id,
                ))
            if blueprint_id:
                versions_query = versions_query.filter(AgentVersionModel.blueprint_id == blueprint_id)
            if run_id or assignment_id:
                required_versions = {a.version_id for a in assignments}
                if captured_version:
                    required_versions.add(captured_version)
                versions_query = versions_query.filter(AgentVersionModel.id.in_(required_versions))
            versions_query = versions_query.order_by(AgentVersionModel.created_at.desc(), AgentVersionModel.id.desc())
            version_records = versions_query.limit(limit).all() if limit else versions_query.all()
            if version_id and not any(v.id == version_id for v in version_records):
                version_records = [selected_version, *version_records[:limit - 1]]
            if limit and blueprint_id and not run_id:
                pinned = []
                if version_id:
                    pinned.append(selected_version)
                for assignment in assignments:
                    active_version = repo.get_version(ctx, assignment.version_id)
                    if active_version.blueprint_id == blueprint_id and not any(record.id == active_version.id for record in pinned):
                        pinned.append(active_version)
                pinned_ids = {record.id for record in pinned}
                version_records = [*pinned, *[record for record in version_records if record.id not in pinned_ids]][:limit]
            selected_configuration = version_id or captured_version or (version_records[0].id if version_records else None)
            blueprint_query = s.query(AgentBlueprintModel).filter_by(organization_id=ctx.organization_id, project_id=project_id)
            if blueprint_id:
                blueprint_query = blueprint_query.filter_by(id=blueprint_id)
            elif limit and version_records:
                blueprint_query = blueprint_query.filter(AgentBlueprintModel.id.in_({v.blueprint_id for v in version_records}))
            blueprint_query = blueprint_query.order_by(AgentBlueprintModel.created_at.desc(), AgentBlueprintModel.id.desc())
            blueprints = [row(x) for x in (blueprint_query.limit(limit).all() if limit else blueprint_query.all())]
            versions = [row(record) for record in version_records]
            # Hold strong references for the duration of the verified projection.
            # SQLAlchemy's weak identity map otherwise re-fetches every audit/version.
            stored_records = {"versions": version_records}
            data = {
                "evaluation_suites": [
                    {"suite_id": suite.suite_id, "evaluation_version": suite.evaluation_version,
                     "aliases": suite.aliases, "name": suite.name,
                     "scenarios": [{"scenario_id": scenario.scenario_id, "name": scenario.name,
                                    "category": scenario.category} for scenario in suite.scenarios]}
                    for suite in get_bench_suite_registry().suites()
                ],
                "blueprints": blueprints,
                "versions": versions,
                "assignments": [row(x) for x in assignments],
            }
            for key, model in {
                "evaluations": BenchEvaluationModel,
                "approvals": ApprovalModel,
                "runs": RunStateModel,
                "audit": AuditEventModel,
            }.items():
                query = s.query(model).filter_by(
                    organization_id=ctx.organization_id, project_id=project_id
                )
                if limit:
                    version_ids = [record.id for record in version_records]
                    if key == "evaluations":
                        query = query.filter(model.version_id.in_(version_ids))
                        if evaluation_id:
                            query = query.filter_by(id=evaluation_id)
                    elif key == "approvals":
                        query = query.filter(model.target_type == "agent_version", model.target_id.in_(version_ids))
                    elif key == "runs":
                        query = query.filter(model.execution_mode != "bench", model.id == run_id) if run_id else query.filter(False)
                    elif key == "audit":
                        query = query.filter(model.resource_id.in_([run_id, blueprint_id, *version_ids, *[a.id for a in assignments]]))
                order = (
                    model.occurred_at
                    if key == "audit"
                    else model.evaluated_at
                    if key == "evaluations"
                    else model.created_at
                )
                query = query.order_by(order.desc(), model.id.desc())
                stored_records[key] = query.limit(limit).all() if limit else query.all()
                data[key] = [row(x) for x in stored_records[key]]
            from database.repositories.audit_repo import AuditRepository
            for audit_event in data["audit"]:
                stored_event = s.get(AuditEventModel, audit_event["id"])
                audit_event["authenticated"] = AuditRepository(s).verify_authenticated_event(stored_event)
                audit_event["integrity_limitation"] = None if audit_event["authenticated"] else "legacy_or_unverified_audit"
            # Stored labels are history, not governance authority. Expose verified
            # eligibility so Studio cannot present a fabricated PASS as actionable.
            for version in data["versions"]:
                stored = s.get(AgentVersionModel, version["id"])
                version["registry"] = AgentActivationRepository(s, db.evidence_signer, permissions).registry_entry(ctx, stored).model_dump(mode="json")
                version["integrity_valid"] = True
                version["bench_eligible"] = False
                version["governance_valid"] = False
                version["regression"] = None
                try:
                    contract = AgentVersion.from_stored(stored)
                    bench_repo = BenchRepository(s, db.evidence_signer)
                    if stored.evaluation_id:
                        version["regression"] = BenchRegressionRepository(s, db.evidence_signer).compare(
                            ctx, stored.id).model_dump(mode="json")
                    for evaluation in data["evaluations"]:
                        if evaluation["version_id"] == version["id"]:
                            evaluation["verified"] = False
                            try:
                                bench_repo.validate_stored(ctx, s.get(BenchEvaluationModel, evaluation["id"]), contract)
                                evaluation["verified"] = True
                            except QualityGateFailedError:
                                pass
                    if stored.status in {"draft", "approved", "published"}:
                        version["bench_eligible"] = bool(bench_repo.get_latest_passing_evaluation(ctx, stored.id))
                    if stored.status in {"approved", "published"} and version["bench_eligible"]:
                        factory.approval_engine.verify_approval(ctx, "agent_version", stored.id, stored.payload_hash, session=s)
                        if stored.status == "published":
                            AgentActivationRepository(s, db.evidence_signer, permissions).known_good(ctx, stored.id)
                        version["governance_valid"] = True
                except VersionIntegrityError:
                    version["integrity_valid"] = False
                except (QualityGateFailedError, ApprovalRequiredError, PayloadHashMismatchError):
                    pass
            for evaluation in data["evaluations"]:
                evaluation.setdefault("verified", False)
                if not isinstance(evaluation["provenance"], dict):
                    evaluation["provenance"] = {}
                if not isinstance(evaluation["details"], list):
                    evaluation["details"] = []
                current_version = next((v for v in data["versions"] if v["id"] == evaluation["version_id"]), None)
                evaluation["regression"] = (current_version.get("regression") if current_version
                    and current_version.get("evaluation_id") == evaluation["id"] else None)
            data["accepted_baselines"] = []
            for blueprint in blueprints:
                try:
                    baseline = BenchRegressionRepository(s, db.evidence_signer).current(ctx, blueprint["id"])
                    if baseline:
                        data["accepted_baselines"].append(baseline.model_dump(mode="json", exclude={"suite_definition", "attestation"}))
                except (QualityGateFailedError, VersionIntegrityError, ValueError):
                    pass
            for approval in data["approvals"]:
                version = next((v for v in data["versions"] if v["id"] == approval["target_id"]), None)
                approval["verified"] = bool(version and version["governance_valid"] and
                                            version["evaluation_id"] == approval["evaluation_id"])
                if approval["verified"]:
                    try:
                        factory.approval_engine.verify_signature(s.get(ApprovalModel, approval["id"]))
                    except ApprovalRequiredError:
                        approval["verified"] = False
            budget = BudgetRepository(s).get_budget(ctx)
            activation_repo = AgentActivationRepository(s, db.evidence_signer, permissions)
            for assignment in data["assignments"]:
                assignment["activation_verified"] = False
                assignment["activation_history"] = []
                assignment["activation_reason"] = "pre_existing_assignment_origin"
                try:
                    history = activation_repo.history(ctx, AgentRepository(s).get_assignment(ctx, assignment["id"]))
                    assignment["activation_history"] = [x.model_dump(mode="json", exclude={"attestation"}) for x in history]
                    assignment["activation_verified"] = bool(history)
                    assignment["activation_reason"] = "verified_activation_history" if history else "pre_existing_assignment_origin"
                except (ValueError, RuntimeError):
                    assignment["activation_reason"] = "activation_integrity_invalid"
            data["runs"] = [run for run in data["runs"] if run["execution_mode"] != "bench"]
            from database.repositories.run_state_repo import RunStateRepository
            for run in data["runs"]:
                try:
                    stored_run = RunStateRepository(s).get_run(ctx, run["id"])
                    run["assignment_provenance_verified"] = RunStateRepository(s).verify_assignment_provenance(stored_run)
                    run.update(run_response(coordinator.stored_result(stored_run)))
                except (ValueError, RuntimeError):
                    run["assignment_provenance_verified"] = False
                    if limit:
                        run["execution_claim_verified"] = False
                        run["prompt"], run["output"] = "", ""
                        run["output_reference"] = None
                        run["usage_availability"] = "unavailable"
            data["budget"] = row(budget) if budget else None
            data["permissions"] = {
                action: permissions.evaluate(action, ctx, ctx.organization_id, project_id).allowed
                for action in (
                    "run:create",
                    "blueprint:create",
                    "version:create",
                    "run:cancel",
                    "version:approve",
                    "version:publish",
                    "bench:accept_baseline",
                    "agent:assign",
                    "agent:rollback",
                )
            }
            if limit:
                for version in data["versions"]:
                    version["configuration_loaded"] = version["id"] == selected_configuration
                    if not version["configuration_loaded"]:
                        for field in ("system_prompt", "metadata", "constraints", "model_policy", "output_contract", "tool_policy", "budget_policy", "evaluation_reference"):
                            version.pop(field, None)
                for evaluation in data["evaluations"]:
                    if evaluation["version_id"] != selected_configuration:
                        evaluation["details"] = []
                import datetime as dt
                data.update(organization_id=ctx.organization_id, project_id=project_id, limit=limit,
                    refreshed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            permissions.enforce("run:read", ctx, ctx.organization_id, project_id, session=s)
        from modules.core.errors import sanitize
        return sanitize(data, credentials=protected_credentials)

    @app.post("/api/projects/{project_id}/blueprints", status_code=201)
    async def create_blueprint(project_id: str, body: BlueprintInput):
        return factory.create_blueprint(
            context(project_id, "blueprint:create"), **body.model_dump()
        )

    @app.get("/api/projects/{project_id}/blueprints/{blueprint_id}/working-copy", response_model=WorkingCopyView)
    async def read_working_copy(project_id: str, blueprint_id: str):
        return sanitize(editor.read(context(project_id), blueprint_id).model_dump(mode="json"), credentials=protected_credentials)

    @app.post("/api/projects/{project_id}/blueprints/{blueprint_id}/working-copy", response_model=WorkingCopyView)
    async def save_working_copy(project_id: str, blueprint_id: str, body: WorkingCopyInput):
        return sanitize(editor.save(context(project_id, "version:create"), blueprint_id, body).model_dump(mode="json"), credentials=protected_credentials)

    @app.post("/api/projects/{project_id}/blueprints/{blueprint_id}/working-copy/discard", response_model=WorkingCopyView)
    async def discard_working_copy(project_id: str, blueprint_id: str, body: GenerationInput):
        return editor.discard(context(project_id, "version:create"), blueprint_id, body)

    @app.post("/api/projects/{project_id}/blueprints/{blueprint_id}/working-copy/versions", status_code=201)
    async def create_candidate(project_id: str, blueprint_id: str, body: GenerationInput):
        context(project_id, "version:create")
        discovery = await model_catalog()
        if not discovery.discovery_valid:
            raise GatewayUnavailableError()
        return editor.candidate(context(project_id, "version:create"), blueprint_id, body)

    @app.get("/api/projects/{project_id}/blueprints/{blueprint_id}/editor-layout", response_model=LayoutView)
    async def read_editor_layout(project_id: str, blueprint_id: str):
        return editor.layout(context(project_id), blueprint_id)

    @app.post("/api/projects/{project_id}/blueprints/{blueprint_id}/editor-layout", response_model=LayoutView)
    async def save_editor_layout(project_id: str, blueprint_id: str, body: LayoutInput):
        return editor.layout(context(project_id, "version:create"), blueprint_id, body)

    @app.post(
        "/api/projects/{project_id}/blueprints/{blueprint_id}/versions", status_code=201
    )
    async def create_version(project_id: str, blueprint_id: str, body: VersionInput):
        context(project_id, "version:create")
        discovery = await model_catalog()
        if not discovery.discovery_valid:
            raise GatewayUnavailableError()
        model_router.resolve_model(body.model)
        return factory.create_version(
            context(project_id, "version:create"),
            blueprint_id=blueprint_id,
            **body.model_dump(),
        )

    from modules.core.errors import public_error, sanitize

    def run_response(result):
        return {**result.model_dump(mode="json", exclude={"raw_response", "execution_evidence"}),
            "id": result.run_id, "session_id": result.assignment_id, "actual_provider": result.provider,
            "input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens, "usage_availability": result.usage.availability}

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse(status_code=500, content=public_error(exc))

    def bench_completion(ctx, result):
        """JSON/SSE completion identifies the persisted, server-verified evaluation."""
        with db.session() as s:
            repo = BenchRepository(s, db.evidence_signer)
            stored = repo.get_evaluation(ctx, result.evaluation_id)
            evaluation = row(stored)
            evaluation["verified"] = False
            try:
                version = AgentVersion.from_stored(AgentRepository(s).get_version(ctx, result.version_id))
                repo.validate_stored(ctx, stored, version)
                evaluation["verified"] = True
                evaluation["regression"] = BenchRegressionRepository(s, db.evidence_signer).compare(
                    ctx, result.version_id).model_dump(mode="json")
            except (QualityGateFailedError, VersionIntegrityError):
                pass
        return sanitize({**result.model_dump(mode="json"), "evaluation": evaluation}, credentials=protected_credentials)

    @app.post("/api/projects/{project_id}/versions/{version_id}/bench")
    async def bench(project_id: str, version_id: str, body: dict, request: Request):
        if (
            body.keys() != {"allow_remote_model"}
            or body["allow_remote_model"] is not True
        ):
            raise HTTPException(
                422,
                "Konfirmasi penggunaan model jarak jauh untuk suite evaluasi Bench diperlukan.",
            )
        ctx = context(project_id, "run:create")
        await require_runtime()
        with db.session() as s:
            v = AgentRepository(s).get_version(ctx, version_id)
            contract = AgentVersion.from_stored(v)
            suite = factory.bench_runner.resolve_suite(contract)
            # Core budget preflight covers every scenario in the authoritative suite.
            for scenario in suite.scenarios:
                coordinator.budget_engine.check_preflight(
                    ctx,
                    v.max_tokens + (len(scenario.prompt) + len(v.system_prompt)) // 3,
                )
            selected_model = v.model
        await adapter.require_model_available(selected_model)
        await model_catalog()

        is_stream = request.headers.get("accept") == "text/event-stream" or request.query_params.get("stream") == "true"
        if is_stream:
            async def event_generator():
                queue = asyncio.Queue()
                async def queue_event(ev_name: str, payload: dict):
                    # Runner completion precedes persistence. The public completion
                    # is emitted only after storage and evidence verification below.
                    if ev_name != "bench.completed":
                        await queue.put((ev_name, sanitize(payload, credentials=protected_credentials)))

                async def run_eval():
                    try:
                        res = await factory.evaluate_version_with_bench(ctx, version_id, on_event=queue_event)
                        await queue.put(("bench.completed", bench_completion(ctx, res)))
                    except Exception as err:
                        await queue.put(("bench.error", public_error(err, correlation_id=ctx.correlation_id)))
                    finally:
                        await queue.put(None)

                eval_task = asyncio.create_task(run_eval())
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    ev_name, payload = item
                    yield f"event: {ev_name}\ndata: {json.dumps(payload)}\n\n"
                await eval_task

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        result = await factory.evaluate_version_with_bench(ctx, version_id)
        return bench_completion(ctx, result)

    @app.post("/api/projects/{project_id}/blueprints/{blueprint_id}/baseline")
    async def accept_baseline(project_id: str, blueprint_id: str, body: BaselineAcceptanceInput):
        ctx = context(project_id, "bench:accept_baseline")
        with db.session(write=True) as s:
            AgentRepository(s).get_blueprint(ctx, blueprint_id)
            evaluation = BenchRepository(s, db.evidence_signer).get_evaluation(ctx, body.evaluation_id)
            if evaluation.blueprint_id != blueprint_id:
                raise TenantIsolationError("Baseline evaluation belongs to another blueprint.")
            return BenchRegressionRepository(s, db.evidence_signer, permissions, factory.approval_engine).accept(ctx, body.evaluation_id,
                expected_baseline_id=body.expected_baseline_id, reason=body.reason, transition=body.suite_transition)

    @app.post("/api/projects/{project_id}/versions/{version_id}/approve")
    async def approve(project_id: str, version_id: str, body: ApprovalInput):
        ctx = context(project_id, "version:approve")
        return factory.approve_version(ctx, version_id, body.comments, expected_payload_hash=body.payload_hash)

    @app.post("/api/projects/{project_id}/versions/{version_id}/publish")
    async def publish(project_id: str, version_id: str):
        ctx = context(project_id, "version:publish")
        return factory.publish_version(ctx, version_id)

    @app.post("/api/projects/{project_id}/assignments", status_code=201)
    async def assign(project_id: str, body: AssignmentInput):
        ctx = context(project_id, "agent:assign")
        return factory.assign_agent(ctx, **body.model_dump())

    @app.get("/api/projects/{project_id}/blueprints/{blueprint_id}/registry")
    async def registry(project_id: str, blueprint_id: str):
        return factory.version_registry(context(project_id), blueprint_id)

    @app.post("/api/projects/{project_id}/assignments/{assignment_id}/rollback")
    async def rollback(project_id: str, assignment_id: str, body: RollbackIntent):
        return factory.rollback_assignment(context(project_id), assignment_id, body)

    @app.post("/api/projects/{project_id}/runs")
    async def run(project_id: str, body: RunInput, request: Request):
        ctx = context(project_id, "run:create")
        if not body.allow_remote_model:
            raise HTTPException(
                422,
                "Konfirmasikan pengiriman instruksi riset melalui ARYN Runtime dan Model Gateway.",
            )
        is_stream = request.headers.get("accept") == "text/event-stream" or request.query_params.get("stream") == "true"
        # Availability is advisory preflight. Identity is captured only by Core
        # after the await; all public metadata comes from that persisted claim.
        cached = None
        from database.repositories.run_state_repo import RunStateRepository
        with db.session() as s:
            existing = RunStateRepository(s).get_run_by_idempotency_key(ctx, body.idempotency_key)
            if existing:
                if (existing.prompt != body.prompt or existing.assignment_id != body.assignment_id
                        or json.loads(existing.effective_limits_json).get("actor_id") != ctx.actor.actor_id):
                    raise IdempotencyConflictError("Key belongs to another input or assignment.")
                cached = coordinator.stored_result(existing)
                if not cached.execution_claim_verified:
                    raise PermissionDeniedError("Historical execution claims are read-only.")
        if cached is None:
            with db.session() as s:
                asgn = AgentRepository(s).get_assignment(ctx, body.assignment_id)
                advisory_model = AgentRepository(s).get_version(ctx, asgn.version_id).model
            await require_runtime()
            await adapter.require_model_available(advisory_model)
            await model_catalog()

        async def execute():
            if cached is not None and cached.status.value not in RunStateRepository.TERMINAL_STATES:
                permissions.enforce("run:read", ctx, ctx.organization_id, ctx.project_id)
                return cached
            result = await coordinator.execute_assigned_agent_turn(body.assignment_id, body.prompt, ctx, body.idempotency_key)
            permissions.enforce("run:read", ctx, ctx.organization_id, ctx.project_id)
            audit.record("studio.run.assignment", ctx, result.run_id,
                AuditStatus.COMPLETED if result.status.value == "completed" else AuditStatus.FAILED,
                {"assignment_id": result.assignment_id, "version_id": result.agent_version_id,
                 "payload_hash": result.agent_payload_hash, "transition_id": result.assignment_transition_id,
                 "actual_model": result.actual_model, "requested_model": result.requested_model,
                 "provider": result.provider, "gateway": result.gateway, "runtime_backend": result.runtime_backend,
                 "status": result.status.value, "trace_available": False})
            return run_response(result)

        if is_stream:
            async def run_stream():
                try:
                    yield f"event: run.requested\ndata: {json.dumps({'assignment_id': body.assignment_id, 'correlation_id': ctx.correlation_id})}\n\n"
                    yield f"event: core.validating\ndata: {json.dumps({'message': 'Core memvalidasi execution claim dan budget'})}\n\n"
                    payload = await execute()
                    if hasattr(payload, "model_dump"):
                        payload = run_response(payload)
                    # Transport completion is a result envelope, not a success claim;
                    # clients inspect the captured status, including outcome_unknown.
                    yield f"event: run.completed\ndata: {json.dumps(payload)}\n\n"
                except Exception as err:
                    error = public_error(err, correlation_id=ctx.correlation_id, run_id=getattr(err, "run_id", None))
                    yield f"event: run.failed\ndata: {json.dumps(error)}\n\n"
            return StreamingResponse(run_stream(), media_type="text/event-stream")
        result = await execute()
        return run_response(result) if hasattr(result, "model_dump") else result

    @app.post("/api/projects/{project_id}/runs/{run_id}/stop", response_model=StopReceipt)
    async def stop_run(project_id: str, run_id: str, body: StopInput):
        ctx = context(project_id, "run:cancel")
        await coordinator.cancel_managed_run(run_id, ctx)
        from database.repositories.run_state_repo import RunStateRepository
        from modules.core.errors import sanitize
        with db.session() as session:
            stored = RunStateRepository(session).get_run(ctx, run_id)
            result = coordinator.stored_result(stored)
            permissions.enforce("run:read", ctx, ctx.organization_id, project_id, session=session)
        return sanitize(StopReceipt(cancellation_confirmed=result.status.value == "cancelled", result=result).model_dump(mode="json"), credentials=protected_credentials)

    from services.api.workflows import register_workflows
    register_workflows(app, coordinator, context, require_runtime)

    assets = ROOT / "apps/web/dist/assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    async def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Endpoint API tidak tersedia.")
        index = ROOT / "apps/web/dist/index.html"
        if not index.exists():
            return fail(
                503, "Frontend belum dibangun. Jalankan scripts/start-studio.ps1."
            )
        return FileResponse(index)

    return app
