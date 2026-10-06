"""Regression tests for centralized endpoint configuration and security validation."""

import os
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest
from starlette.testclient import TestClient

from database.connection import DatabaseManager, create_db_engine, init_db
from packages.config import ARYNSettings, get_settings
from packages.model_adapters.gateway import GatewaySettings, NineRouterGateway
from packages.runtime_adapters.hermes import HermesRuntimeAdapter, RuntimeSecurityError
from services.api.studio import create_app
from tests.studio_runtime import IsolatedTestRuntime


def test_env_override_runtime_url(monkeypatch):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", "http://127.0.0.1:8645")
    settings = get_settings()
    assert settings.runtime_base_url == "http://127.0.0.1:8645"
    assert settings.runtime_port == 8645

    adapter = HermesRuntimeAdapter()
    assert adapter.base_url == "http://127.0.0.1:8645"


def test_env_override_9router_url(monkeypatch):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_9ROUTER_BASE_URL", "http://127.0.0.1:20129/v1")
    settings = get_settings()
    assert settings.nine_router_base_url == "http://127.0.0.1:20129/v1"

    gw_settings = GatewaySettings.from_env()
    assert gw_settings.base_url == "http://127.0.0.1:20129/v1"


def test_studio_host_port_override_consistent(monkeypatch, tmp_path):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_STUDIO_HOST", "127.0.0.1")
    monkeypatch.setenv("ARYN_STUDIO_PORT", "8715")
    settings = get_settings()
    assert settings.studio_host == "127.0.0.1"
    assert settings.studio_port == 8715
    assert settings.studio_origin == "http://127.0.0.1:8715"

    db = DatabaseManager(create_db_engine(f"sqlite:///{tmp_path / 'studio.sqlite3'}"))
    init_db(db.engine)
    runtime = IsolatedTestRuntime()
    app = create_app(db, runtime, origin=settings.studio_origin, testing=True)
    with TestClient(app, base_url=settings.studio_origin, client=("127.0.0.1", 50000)) as client:
        resp = client.post("/api/session", json={}, headers={"Origin": settings.studio_origin})
        assert resp.status_code == 200
    db.engine.dispose()


def test_non_loopback_rejected_in_local_mode(monkeypatch):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", "http://192.168.1.100:8642")
    with pytest.raises(ValueError, match="must bind only to loopback"):
        ARYNSettings.from_env()

    with pytest.raises(RuntimeSecurityError, match="must bind only to loopback"):
        HermesRuntimeAdapter(base_url="http://192.168.1.100:8642", model_gateway=MagicMock())

    monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("ARYN_9ROUTER_BASE_URL", "http://10.0.0.1:20128/v1")
    with pytest.raises(ValueError, match="must bind only to loopback"):
        ARYNSettings.from_env()

    monkeypatch.setenv("ARYN_9ROUTER_BASE_URL", "http://127.0.0.1:20128/v1")
    monkeypatch.setenv("ARYN_STUDIO_HOST", "192.168.1.50")
    with pytest.raises(ValueError, match="must be a loopback address"):
        ARYNSettings.from_env()

    monkeypatch.setenv("ARYN_STUDIO_HOST", "127.0.0.1")
    with pytest.raises(ValueError, match="Studio origin must be an explicit loopback port"):
        create_app(origin="http://192.168.1.50:8710", testing=True)


@pytest.mark.parametrize("invalid_url", [
    "http://user:secret@127.0.0.1:8642",
    "http://127.0.0.1:8642?token=secret",
    "http://127.0.0.1:8642#fragment",
    "ftp://127.0.0.1:8642",
])
def test_runtime_url_credentials_and_queries_rejected(monkeypatch, invalid_url):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", invalid_url)
    with pytest.raises(ValueError):
        ARYNSettings.from_env()

    with pytest.raises(RuntimeSecurityError):
        HermesRuntimeAdapter(base_url=invalid_url, model_gateway=MagicMock())


@pytest.mark.parametrize("invalid_url", [
    "http://user:secret@127.0.0.1:20128/v1",
    "http://127.0.0.1:20128/v1?token=secret",
    "http://127.0.0.1:20128/v1#fragment",
    "http://127.0.0.1:20128/v2",
])
def test_9router_url_credentials_and_invalid_paths_rejected(monkeypatch, invalid_url):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_9ROUTER_BASE_URL", invalid_url)
    with pytest.raises(ValueError):
        ARYNSettings.from_env()

    with pytest.raises(ValueError):
        GatewaySettings(base_url=invalid_url)


def test_missing_required_config_non_development_fails_closed(monkeypatch):
    monkeypatch.setenv("ARYN_ENV", "production")
    monkeypatch.delenv("ARYN_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("ARYN_9ROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("ARYN_STUDIO_HOST", raising=False)
    monkeypatch.delenv("ARYN_STUDIO_PORT", raising=False)

    with pytest.raises(ValueError, match="ARYN_STUDIO_HOST is required"):
        ARYNSettings.from_env()

    monkeypatch.setenv("ARYN_STUDIO_HOST", "127.0.0.1")
    with pytest.raises(ValueError, match="ARYN_STUDIO_PORT is required"):
        ARYNSettings.from_env()

    monkeypatch.setenv("ARYN_STUDIO_PORT", "8710")
    with pytest.raises(ValueError, match="ARYN_RUNTIME_BASE_URL is required"):
        ARYNSettings.from_env()

    monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", "http://127.0.0.1:8642")
    with pytest.raises(ValueError, match="ARYN_9ROUTER_BASE_URL is required"):
        ARYNSettings.from_env()


def test_9router_db_never_read_for_secret(monkeypatch):
    assert not hasattr(GatewaySettings, "_local_9router_key")
    assert not hasattr(NineRouterGateway, "_local_9router_key")

    monkeypatch.delenv("ARYN_9ROUTER_API_KEY", raising=False)
    with patch("sqlite3.connect") as mock_sqlite:
        settings = GatewaySettings.from_env()
        assert settings.api_key.get_secret_value() == ""
        mock_sqlite.assert_not_called()


def test_gateway_key_not_leaked_to_api_log_or_audit(monkeypatch, tmp_path):
    secret_key = "very-confidential-gateway-key-xyz-987"
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_9ROUTER_API_KEY", secret_key)
    monkeypatch.setenv("API_SERVER_KEY", "isolated-runtime-token-secret-123")

    db = DatabaseManager(create_db_engine(f"sqlite:///{tmp_path / 'studio.sqlite3'}"))
    init_db(db.engine)
    runtime = IsolatedTestRuntime()
    app = create_app(db, runtime, origin="http://127.0.0.1:8710", testing=True)

    with TestClient(app, base_url="http://127.0.0.1:8710", client=("127.0.0.1", 50000)) as client:
        # 1. Verify boundary blocks the secret from being sent in payloads
        resp = client.post(
            "/api/session",
            json={"leaked": secret_key},
            headers={"Origin": "http://127.0.0.1:8710"},
        )
        assert resp.status_code == 422
        assert "Credential server tidak boleh disertakan" in resp.text

        # 2. Verify normal session response does not leak the key
        valid_resp = client.post(
            "/api/session",
            json={},
            headers={"Origin": "http://127.0.0.1:8710"},
        )
        assert valid_resp.status_code == 200
        assert secret_key not in valid_resp.text

    # 3. Verify audit log records in database do not contain the secret
    with db.session() as s:
        from database.schema import AuditEventModel
        logs = s.query(AuditEventModel).all()
        for log_entry in logs:
            assert secret_key not in (log_entry.details_json or "")
    db.engine.dispose()


def test_launcher_scripts_use_centralized_environment_variables():
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    start_runtime = (scripts_dir / "start-runtime-9router.ps1").read_text(encoding="utf-8")
    start_studio = (scripts_dir / "start-studio.ps1").read_text(encoding="utf-8")
    start_aryn = (scripts_dir / "start-aryn.ps1").read_text(encoding="utf-8")

    # Verify start-runtime-9router.ps1
    assert "$env:ARYN_RUNTIME_BASE_URL" in start_runtime
    assert "$env:ARYN_9ROUTER_BASE_URL" in start_runtime
    assert "$env:API_SERVER_KEY" in start_runtime
    # Must NOT enforce hardcoded port 8642
    assert "if ($Port -ne 8642)" not in start_runtime

    # Verify start-studio.ps1
    assert "$env:ARYN_STUDIO_HOST" in start_studio
    assert "$env:ARYN_STUDIO_PORT" in start_studio

    # Verify start-aryn.ps1 loads environment and passes ephemeral key
    for script in (start_aryn, start_runtime, start_studio):
        assert "Initialize-ArynConfiguration" in script
        assert "Initialize-ArynRuntimeAuthentication" in script
        assert "http://127.0.0.1:8642" not in script
        assert "http://127.0.0.1:20128/v1" not in script


def test_development_defaults_are_centralized(monkeypatch):
    for name in ("ARYN_ENV", "ARYN_STUDIO_HOST", "ARYN_STUDIO_PORT",
                 "ARYN_RUNTIME_BASE_URL", "ARYN_9ROUTER_BASE_URL", "ARYN_9ROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings == ARYNSettings()
    assert GatewaySettings() == settings.gateway_settings


def test_gateway_uses_centralized_snapshot_without_own_env_reads(monkeypatch):
    centralized = ARYNSettings(nine_router_base_url="http://localhost:20222/v1",
                              nine_router_api_key="test-central-key")
    monkeypatch.setattr("packages.config.get_settings", lambda: centralized)
    monkeypatch.setenv("ARYN_9ROUTER_BASE_URL", "http://127.0.0.1:20129/v1")
    assert GatewaySettings.from_env() == centralized.gateway_settings
    assert GatewaySettings() == centralized.gateway_settings
    assert "test-central-key" not in repr(GatewaySettings())


@pytest.mark.parametrize("factory", [get_settings, GatewaySettings.from_env, GatewaySettings,
                                    lambda: ARYNSettings(aryn_env="production")])
def test_every_default_configuration_path_fails_closed_in_production(monkeypatch, factory):
    monkeypatch.setenv("ARYN_ENV", "production")
    for name in ("ARYN_STUDIO_HOST", "ARYN_STUDIO_PORT", "ARYN_RUNTIME_BASE_URL", "ARYN_9ROUTER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="ARYN_STUDIO_HOST is required"):
        factory()


def test_centralized_endpoint_normalization_is_consistent(monkeypatch):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", " http://localhost:8645/ ")
    monkeypatch.setenv("ARYN_9ROUTER_BASE_URL", " http://localhost:20129/v1/ ")
    monkeypatch.setenv("ARYN_STUDIO_HOST", " LOCALHOST ")
    settings = get_settings()
    assert settings.studio_host == "localhost"
    assert settings.runtime_base_url == HermesRuntimeAdapter().base_url == "http://localhost:8645"
    assert settings.nine_router_base_url == GatewaySettings.from_env().base_url == "http://localhost:20129/v1"


@pytest.mark.parametrize("invalid", [False, True])
def test_launcher_config_output_and_errors_never_expose_secrets(monkeypatch, invalid):
    monkeypatch.setenv("ARYN_ENV", "development")
    monkeypatch.setenv("ARYN_9ROUTER_API_KEY", "isolated-gateway-output-secret")
    monkeypatch.setenv("API_SERVER_KEY", "isolated-runtime-output-secret")
    if invalid:
        monkeypatch.setenv("ARYN_RUNTIME_BASE_URL", "http://user:isolated-runtime-output-secret@127.0.0.1:8642")
    result = subprocess.run([sys.executable, "-m", "packages.config"], capture_output=True, text=True, timeout=15)
    assert "isolated-gateway-output-secret" not in result.stdout + result.stderr
    assert "isolated-runtime-output-secret" not in result.stdout + result.stderr
    if invalid:
        assert result.returncode != 0
    else:
        assert result.returncode == 0, result.stderr
        assert set(json.loads(result.stdout)) == {"ARYN_ENV", "ARYN_STUDIO_HOST", "ARYN_STUDIO_PORT",
                                               "ARYN_RUNTIME_BASE_URL", "ARYN_9ROUTER_BASE_URL"}
