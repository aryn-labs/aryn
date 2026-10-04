"""Loopback-only Studio application boundary. This is development access, not production auth.

Browser identity claims are never accepted. The server issues a local opaque session
and constructs signed Core contexts for a single provisioned development principal.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from database.connection import DatabaseManager, create_db_engine
from database.repositories.agent_repo import AgentRepository
from database.repositories.bench_repo import BenchRepository
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
    ApprovalModel,
    AuditEventModel,
    BenchEvaluationModel,
    OrganizationModel,
    RunStateModel,
)
from modules.agent_factory.service import AgentFactoryService, ForbiddenToolError
from modules.bench.quality_gate import QualityGateFailedError
from modules.bench.runner import BenchRunner
from modules.bench.scenarios import get_standard_research_bench_scenarios
from modules.core.approvals.engine import (
    ApprovalRequiredError,
    PayloadHashMismatchError,
    UnauthorizedApproverError,
)
from modules.core.audit.logger import AuditLogger
from modules.core.identity.binder import TrustedIdentityBinder
from modules.core.permissions.engine import PermissionDeniedError, PermissionEngine
from modules.core.usage.engine import BudgetExceededError
from modules.core.workflows.coordinator import RunCoordinator
from packages.contracts.bench import RESEARCH_BENCH_VERSION
from packages.contracts.agent import VersionIntegrityError
from packages.contracts.core import AuditStatus
from packages.model_adapters import ModelRouter, ModelRoutingError
from packages.runtime_adapters import HermesAdapterError, HermesRuntimeAdapter

ROOT = Path(__file__).resolve().parents[2]
DEV_ORG = "org_studio_local"
DEV_ACTOR = "studio_local_owner"
DEV_PROJECT = "proj_studio_research"
COOKIE = "aryn_studio_session"
SESSION_TTL = 8 * 3600
SUITE_VERSION = RESEARCH_BENCH_VERSION


class BlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(
        min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str = Field(default="", max_length=2000)


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
    """Read only the existing local Hermes key. Never serialize/log this value."""
    if os.getenv("API_SERVER_KEY"):
        return os.environ["API_SERVER_KEY"]
    path = Path.home() / "AppData/Local/hermes/.env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def row(model):
    data = {c.name: getattr(model, c.name) for c in model.__table__.columns}
    for name in list(data):
        value = data[name]
        if hasattr(value, "isoformat"):
            data[name] = value.isoformat() + ("Z" if value.tzinfo is None else "")
        if name.endswith("_json"):
            data[name.removesuffix("_json")] = json.loads(data.pop(name) or "{}")
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
    origin="http://127.0.0.1:8710",
    testing=False,
):
    if origin not in {f"http://127.0.0.1:{p}" for p in range(1024, 65536)}:
        raise ValueError("Studio origin must be an explicit 127.0.0.1 loopback port.")
    if db is None:
        path = ROOT / ".local/studio.sqlite3"
        path.parent.mkdir(exist_ok=True)
        engine = create_db_engine(f"sqlite:///{path.as_posix()}")
        migrate(engine)
        db = DatabaseManager(engine=engine)
    binder = TrustedIdentityBinder(secret_key=secrets.token_bytes(32))
    permissions = PermissionEngine(db_manager=db, identity_binder=binder)
    audit = AuditLogger(db_manager=db)
    adapter = runtime or StudioHermesAdapter(api_key=runtime_key(), timeout=10)
    factory = AgentFactoryService(
        db, BenchRunner(adapter), permission_engine=permissions, audit_logger=audit
    )
    coordinator = RunCoordinator(
        adapter, permission_engine=permissions, audit_logger=audit, db_manager=db
    )
    sessions = {}
    mutation_lock = asyncio.Lock()
    catalog = [
        s.model_dump(mode="json")
        for s in ModelRouter().catalog.values()
        if s.provider.value == "nous"
    ]
    allowed_models = {s["model_id"] for s in catalog}

    # Provision only dedicated development scope. Do not re-grant a revoked membership on restart.
    with db.session() as s:
        repo = OrganizationRepository(s)
        if not s.get(OrganizationModel, DEV_ORG):
            repo.create_organization(DEV_ORG, "ARYN Lokal", "aryn-studio-local")
            repo.add_member(DEV_ORG, DEV_ACTOR, role="admin")
            ctx = binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
            repo.create_project(
                ctx, DEV_PROJECT, "Laboratorium Riset", "laboratorium-riset"
            )
            BudgetRepository(s).get_or_create_budget(ctx)

    recovery_ctx = binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    coordinator.recover_in_flight_runs(recovery_ctx)
    with db.session() as s:
        interrupted = (
            s.query(AgentVersionModel)
            .join(AgentBlueprintModel)
            .filter(
                AgentBlueprintModel.organization_id == DEV_ORG,
                AgentVersionModel.status == "evaluating",
            )
            .all()
        )
        for version in interrupted:
            version.status = "rejected"
            audit.record(
                "bench.evaluation.interrupted",
                recovery_ctx,
                version.id,
                AuditStatus.FAILED,
                {
                    "reason": "Evaluasi terhenti saat layanan dimulai ulang. Jalankan Bench kembali."
                },
            )

    app = FastAPI(
        title="ARYN Studio — API lokal", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.db = db
    app.state.factory = factory
    app.state.binder = binder
    app.state.coordinator = coordinator
    app.state.sessions = sessions

    def fail(code, message):
        return JSONResponse({"message": message}, status_code=code)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
            return fail(403, "Studio hanya dapat diakses melalui loopback lokal.")
        if request.headers.get("host") != origin.removeprefix("http://"):
            return fail(403, "Host tidak diizinkan. Gunakan alamat loopback Studio.")
        is_api = request.url.path.startswith("/api/")
        if is_api:
            supplied_origin = request.headers.get("origin")
            if supplied_origin and supplied_origin != origin:
                return fail(403, "Origin permintaan tidak diizinkan.")
            if request.method not in {"GET", "HEAD"}:
                if (
                    supplied_origin != origin
                    or request.headers.get("sec-fetch-site", "same-origin")
                    != "same-origin"
                ):
                    return fail(403, "Mutasi harus berasal dari halaman Studio lokal.")
                if len(await request.body()) > 65536:
                    return fail(413, "Isi permintaan terlalu besar.")
            if request.url.path != "/api/session":
                session = sessions.get(request.cookies.get(COOKIE, ""))
                if not session or session["expires"] < time.time():
                    return fail(401, "Sesi development berakhir. Muat ulang Studio.")
                if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
                    request.headers.get("x-csrf-token", ""), session["csrf"]
                ):
                    return fail(
                        403, "Token keamanan sesi tidak valid. Muat ulang Studio."
                    )
        if (
            is_api
            and request.method not in {"GET", "HEAD"}
            and request.url.path != "/api/session"
        ):
            async with mutation_lock:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if is_api:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return fail(
            422,
            "Periksa formulir: format, panjang, atau nilai belum sesuai. Klaim identitas dari browser tidak diterima.",
        )

    exception_map = {
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
            "Hermes belum dapat menyelesaikan permintaan. Periksa koneksi, kredensial server, dan batas tool.",
        ),
        RuntimeError: (
            502,
            "Runtime tidak menyelesaikan eksekusi. Kegagalan dicatat oleh Core; periksa riwayat sebelum mencoba kembali.",
        ),
    }
    for error_type, (code, message) in exception_map.items():

        async def handler(request, exc, code=code, message=message):
            return fail(code, message)

        app.add_exception_handler(error_type, handler)

    def context(project_id, action="run:read"):
        ctx = binder.create_trusted_context(DEV_ACTOR, DEV_ORG, project_id)
        try:
            permissions.enforce(action, ctx, DEV_ORG, project_id)
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

    def evidence(ctx, version_id):
        with db.session() as s:
            version = AgentRepository(s).get_version(ctx, version_id)
            result = BenchRepository(s, db.evidence_signer).get_latest_passing_evaluation(ctx, version_id)
            if not result:
                raise QualityGateFailedError("Missing current, complete Bench evidence")
            return row(version)

    async def runtime_status():
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
                "message": "Hermes terhubung · tanpa tool"
                if ready
                else "Runtime dibatasi: seluruh toolset harus dinonaktifkan.",
                "readiness": health.details.get("status", "unknown"),
            }
        except Exception:
            return {
                "connected": False,
                "ready": False,
                "message": "Hermes tidak terhubung atau kredensial server belum valid.",
            }

    async def require_runtime():
        if not (await runtime_status())["ready"]:
            raise HTTPException(
                503,
                "Hermes belum siap. Seluruh toolset harus dinonaktifkan dan kredensial server harus valid.",
            )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return fail(exc.status_code, str(exc.detail))

    @app.post("/api/session")
    async def local_session(request: Request):
        # No roles, tokens, actor IDs, or identity input from the browser.
        if (await request.body()) not in {b"", b"{}"}:
            raise HTTPException(
                422, "Sesi development diterbitkan server tanpa input identitas."
            )
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

    @app.get("/api/workspace")
    async def workspace():
        ctx = context(DEV_PROJECT)
        with db.session() as s:
            repo = OrganizationRepository(s)
            projects = [
                row(p)
                for p in repo.list_projects(ctx)
                if permissions.evaluate(
                    "run:read",
                    binder.create_trusted_context(DEV_ACTOR, DEV_ORG, p.id),
                    DEV_ORG,
                    p.id,
                ).allowed
            ]
            member = repo.get_member(DEV_ORG, DEV_ACTOR)
            role = member.role
        return {
            "organization": {"id": DEV_ORG, "name": "ARYN Lokal"},
            "projects": projects,
            "user": {"name": "Pemilik development", "id": DEV_ACTOR, "role": role},
            "models": catalog,
            "runtime": await runtime_status(),
            "mode": "isolated-test" if testing else "development",
        }

    @app.get("/api/projects/{project_id}/snapshot")
    async def snapshot(project_id: str):
        ctx = context(project_id)
        with db.session() as s:
            blueprints = [row(x) for x in AgentRepository(s).list_blueprints(ctx)]
            versions = [
                row(x)
                for x in s.query(AgentVersionModel)
                .join(AgentBlueprintModel)
                .filter(
                    AgentBlueprintModel.organization_id == DEV_ORG,
                    AgentBlueprintModel.project_id == project_id,
                )
                .order_by(AgentVersionModel.created_at.desc())
                .all()
            ]
            data = {
                "blueprints": blueprints,
                "versions": versions,
                "assignments": [
                    row(x) for x in AgentRepository(s).list_assignments(ctx)
                ],
            }
            for key, model in {
                "evaluations": BenchEvaluationModel,
                "approvals": ApprovalModel,
                "runs": RunStateModel,
                "audit": AuditEventModel,
            }.items():
                query = s.query(model).filter_by(
                    organization_id=DEV_ORG, project_id=project_id
                )
                order = (
                    model.occurred_at
                    if key == "audit"
                    else model.evaluated_at
                    if key == "evaluations"
                    else model.created_at
                )
                data[key] = [row(x) for x in query.order_by(order.desc()).all()]
            budget = BudgetRepository(s).get_budget(ctx)
            data["budget"] = row(budget) if budget else None
            data["permissions"] = {
                action: permissions.evaluate(action, ctx, DEV_ORG, project_id).allowed
                for action in (
                    "run:create",
                    "version:approve",
                    "version:publish",
                    "agent:assign",
                )
            }
        return data

    @app.post("/api/projects/{project_id}/blueprints", status_code=201)
    async def create_blueprint(project_id: str, body: BlueprintInput):
        return factory.create_blueprint(
            context(project_id, "blueprint:create"), **body.model_dump()
        )

    @app.post(
        "/api/projects/{project_id}/blueprints/{blueprint_id}/versions", status_code=201
    )
    async def create_version(project_id: str, blueprint_id: str, body: VersionInput):
        if body.model not in allowed_models:
            raise ModelRoutingError("Studio only supports explicit Hermes/Nous models")
        return factory.create_version(
            context(project_id, "version:create"),
            blueprint_id=blueprint_id,
            **body.model_dump(),
        )

    @app.post("/api/projects/{project_id}/versions/{version_id}/bench")
    async def bench(project_id: str, version_id: str, body: dict):
        if (
            body.keys() != {"allow_remote_model"}
            or body["allow_remote_model"] is not True
        ):
            raise HTTPException(
                422,
                "Konfirmasi penggunaan model jarak jauh untuk empat skenario Bench diperlukan.",
            )
        ctx = context(project_id, "run:create")
        await require_runtime()
        with db.session() as s:
            v = AgentRepository(s).get_version(ctx, version_id)
            if v.model not in allowed_models:
                raise ModelRoutingError("Invalid Studio model")
            # The existing budget is per runtime turn, not per suite. Include
            # input for every fixed scenario before dispatching any of them.
            for scenario in get_standard_research_bench_scenarios():
                coordinator.budget_engine.check_preflight(
                    ctx,
                    v.max_tokens + (len(scenario.prompt) + len(v.system_prompt)) // 3,
                )
        result = await factory.evaluate_version_with_bench(ctx, version_id)
        from packages.contracts.runtime import RunUsage

        coordinator.budget_engine.record_usage(
            ctx,
            RunUsage(total_tokens=sum(r.total_tokens for r in result.scenario_results)),
        )
        return result

    @app.post("/api/projects/{project_id}/versions/{version_id}/approve")
    async def approve(project_id: str, version_id: str, body: ApprovalInput):
        ctx = context(project_id, "version:approve")
        v = evidence(ctx, version_id)
        if body.payload_hash != v["payload_hash"]:
            raise PayloadHashMismatchError(
                "Browser review does not match persisted version"
            )
        return factory.approve_version(ctx, version_id, body.comments)

    @app.post("/api/projects/{project_id}/versions/{version_id}/publish")
    async def publish(project_id: str, version_id: str):
        ctx = context(project_id, "version:publish")
        evidence(ctx, version_id)
        return factory.publish_version(ctx, version_id)

    @app.post("/api/projects/{project_id}/assignments", status_code=201)
    async def assign(project_id: str, body: AssignmentInput):
        ctx = context(project_id, "agent:assign")
        return factory.assign_agent(ctx, **body.model_dump())

    @app.post("/api/projects/{project_id}/runs")
    async def run(project_id: str, body: RunInput):
        ctx = context(project_id, "run:create")
        if not body.allow_remote_model:
            raise HTTPException(
                422,
                "Pilih dan konfirmasikan pengiriman instruksi riset ke model jarak jauh melalui Hermes.",
            )
        # Replays return saved results even when Hermes is subsequently disconnected.
        with db.session() as s:
            from database.repositories.run_state_repo import RunStateRepository

            existing = RunStateRepository(s).get_run_by_idempotency_key(
                ctx, body.idempotency_key
            )
            if existing:
                if (
                    existing.prompt != body.prompt
                    or existing.session_id != body.assignment_id
                ):
                    raise HTTPException(
                        409,
                        "Kunci permintaan telah dipakai untuk input atau penugasan berbeda.",
                    )
                if existing.status == "completed":
                    return row(existing)
                raise HTTPException(
                    409,
                    "Permintaan ini sudah diproses. Periksa riwayat sebelum mencoba kembali.",
                )
            asgn = AgentRepository(s).get_assignment(ctx, body.assignment_id)
            v = AgentRepository(s).get_version(ctx, asgn.version_id)
            if (
                asgn.status != "active"
                or v.model not in allowed_models
                or v.status != "published"
            ):
                raise PermissionDeniedError(
                    "Inactive assignment or unpublished version"
                )
            coordinator.budget_engine.check_preflight(
                ctx, v.max_tokens + (len(body.prompt) + len(v.system_prompt)) // 3
            )
            assigned_version_id = v.id
        await require_runtime()
        # Core binds all configuration from DB, browser supplies only task input.
        result = await coordinator.execute_assigned_agent_turn(
            body.assignment_id, body.prompt, ctx, body.idempotency_key
        )
        with db.session() as s:
            saved = s.get(RunStateModel, result.run_id)
            saved.session_id = body.assignment_id
            saved.model = result.model
            audit.record(
                "studio.run.assignment",
                ctx,
                result.run_id,
                AuditStatus.COMPLETED,
                {
                    "assignment_id": body.assignment_id,
                    "version_id": assigned_version_id,
                    "actual_model": result.model,
                    "runtime": "Hermes",
                    "trace_available": False,
                },
            )
        return result

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
