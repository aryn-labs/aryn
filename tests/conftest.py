"""Global Pytest Configuration and Security Fixtures for ARYN Test Suite.

Enforces explicit cryptographic secrets for development and test execution.
Strictly prohibits default or hardcoded secrets in production source files.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Generator

import pytest

from modules.core.identity.binder import TrustedIdentityBinder
from packages.contracts.core import SecurityContext

TEST_IDENTITY_SECRET = "aryn-test-explicit-entropy-secret-key-32b-secure"


def pytest_addoption(parser):
    parser.addoption("--backend-shard", default=None, help="Deterministic offline backend partition, INDEX/COUNT")


def pytest_collection_modifyitems(items, config):
    """A normal regression run must never submit a live model request."""
    model_tests = {
        "test_live_end_to_end_smoke",
        "test_live_hermes_assigned_research_agent_run",
        "test_live_hermes_run_lifecycle_and_cancellation",
    }
    if os.getenv("ARYN_RUN_LIVE_MODEL_TESTS") != "1":
        for item in items:
            if item.name in model_tests:
                item.add_marker(pytest.mark.skip(reason="Live model tests require explicit opt-in after owner authorization."))
    shard = config.getoption("backend_shard")
    if shard:
        from tests.backend_selection import select_backend_tests
        selected, full = select_backend_tests(items, shard)
        deselected = [item for item in items if item not in selected]
        config._aryn_backend_collection = full
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def pytest_collection_finish(session):
    shard = session.config.getoption("backend_shard")
    if shard:
        path = Path(".local/backend-selection.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"platform": os.name, "shard": shard,
            "commit": os.getenv("GITHUB_SHA"), "complete": session.config._aryn_backend_collection,
            "selected": [item.nodeid for item in session.items]}, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def setup_test_identity_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Ensures an explicit test identity secret is configured for all tests.
    
    Guarantees no component attempts to use a hardcoded default secret.
    """
    monkeypatch.setenv("ARYN_IDENTITY_SECRET", TEST_IDENTITY_SECRET)
    monkeypatch.setenv("ARYN_AUTH_MODE", "local-development")
    yield


@pytest.fixture
def identity_binder() -> TrustedIdentityBinder:
    """Provides a trusted identity binder initialized with an explicit test secret."""
    return TrustedIdentityBinder(secret_key=TEST_IDENTITY_SECRET)


def bind_test_context(
    context: SecurityContext,
    binder: TrustedIdentityBinder | None = None,
    secret_key: str | None = None,
) -> SecurityContext:
    """Helper for tests to bind authoritative identity tokens onto test SecurityContext instances."""
    active_binder = binder or TrustedIdentityBinder(secret_key=secret_key or TEST_IDENTITY_SECRET)
    return active_binder.bind_context(context)


@pytest.fixture
def lifecycle(tmp_path, request):
    from database.connection import DatabaseManager, create_db_engine
    from database.repositories.organization_repo import OrganizationRepository
    from database.schema import Base
    from modules.agent_factory.service import AgentFactoryService
    from modules.bench.runner import BenchRunner
    from packages.contracts.core import Actor
    from tests.studio_runtime import IsolatedTestRuntime

    engine = create_db_engine(f"sqlite:///{(tmp_path / 'batch.sqlite3').as_posix()}")
    if getattr(request, "param", "metadata") == "migrations":
        from services.api.studio import migrate
        migrate(engine)
    else:
        # SQLite's legacy driver otherwise autocommits each CREATE TABLE/INDEX.
        # Build the complete disposable schema and all protection triggers in
        # one real transaction, avoiding hundreds of separate durable writes.
        with engine.begin() as connection:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN")
            Base.metadata.create_all(connection)
    db = DatabaseManager(engine)
    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="owner", organization_id="org", roles=["admin"]),
        organization_id="org", project_id="project",
    ))
    with db.session() as s:
        repo = OrganizationRepository(s)
        repo.create_organization("org", "Test", "test")
        repo.add_member("org", "owner", "admin")
        repo.create_project(ctx, "project", "Test", "test")
    runtime = IsolatedTestRuntime()
    factory = AgentFactoryService(db, BenchRunner(runtime))
    bp = factory.create_blueprint(ctx, "Integrity", "integrity")
    version = factory.create_version(
        ctx, bp.id, "1.0.0", "Follow research safety guidelines.", "mock-fast",
        metadata={"security": {"tools": "denied"}},
    )
    yield db, ctx, runtime, factory, bp, version
    engine.dispose()

