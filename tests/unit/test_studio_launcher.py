"""Launcher wiring only; never starts services or performs model inference."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def launcher_tree(tmp_path):
    root = Path(__file__).resolve().parents[2]
    isolated = tmp_path / "aryn"
    scripts = isolated / "scripts"
    scripts.mkdir(parents=True)
    for name in ("aryn-config.ps1", "start-aryn.ps1", "start-runtime-9router.ps1", "start-studio.ps1"):
        shutil.copyfile(root / "scripts" / name, scripts / name)
    packages = isolated / "packages"
    packages.mkdir()
    for name in ("__init__.py", "config.py"):
        shutil.copyfile(root / "packages" / name, packages / name)
    return isolated


def launcher_env(**overrides):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("ARYN_") and key != "API_SERVER_KEY"}
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return {**env, **overrides}


def run_launcher(root, name, env, *args):
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("Windows PowerShell is not installed")
    return subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(root / "scripts" / name), *args],
                          env=env, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("runtime_fails", [False, True])
def test_combined_launcher_shares_ephemeral_auth_and_stops_on_runtime_failure(launcher_tree, runtime_fails):
    scripts = launcher_tree / "scripts"
    (launcher_tree / ".env").write_text("API_SERVER_KEY=must-not-load-persisted-token\n", encoding="utf-8")
    (scripts / "start-runtime-9router.ps1").write_text(
        "throw 'isolated runtime failure'" if runtime_fails else
        "param([switch]$CheckOnly)\n"
        "if (-not $env:API_SERVER_KEY -or $env:API_SERVER_KEY -eq 'must-not-load-persisted-token') "
        "{ throw 'missing ephemeral authentication' }\n"
        "$env:ARYN_LAUNCH_TEST_AUTH = $env:API_SERVER_KEY\n"
        "Write-Output 'isolated runtime ready'",
        encoding="utf-8",
    )
    (scripts / "start-studio.ps1").write_text(
        "param([switch]$NoBrowser, [switch]$SkipInstall, [switch]$SkipBuild, [switch]$CheckOnly)\n"
        "if (-not $env:API_SERVER_KEY -or $env:API_SERVER_KEY -ne $env:ARYN_LAUNCH_TEST_AUTH) "
        "{ throw 'runtime authentication was not inherited' }\n"
        "if (-not ($NoBrowser -and $SkipInstall -and $SkipBuild)) { throw 'flags were not forwarded' }\n"
        "Write-Output 'isolated Studio ready with shared authentication'",
        encoding="utf-8",
    )
    result = run_launcher(launcher_tree, "start-aryn.ps1", launcher_env(),
                          "-NoBrowser", "-SkipInstall", "-SkipBuild")
    if runtime_fails:
        assert result.returncode != 0
        assert "Studio ready" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "Studio ready with shared authentication" in result.stdout
    assert "must-not-load-persisted-token" not in result.stdout + result.stderr
    assert (launcher_tree / ".env").read_text() == "API_SERVER_KEY=must-not-load-persisted-token\n"


@pytest.mark.parametrize("name", ["start-aryn.ps1", "start-runtime-9router.ps1", "start-studio.ps1"])
@pytest.mark.parametrize("missing", ["ARYN_RUNTIME_BASE_URL", "ARYN_9ROUTER_BASE_URL",
                                   "ARYN_STUDIO_HOST", "ARYN_STUDIO_PORT"])
def test_launchers_non_development_missing_endpoint_fail_before_start(launcher_tree, name, missing):
    values = dict(ARYN_ENV="production", ARYN_RUNTIME_BASE_URL="http://127.0.0.1:8645",
                  ARYN_9ROUTER_BASE_URL="http://127.0.0.1:20129/v1",
                  ARYN_STUDIO_HOST="localhost", ARYN_STUDIO_PORT="8715",
                  ARYN_9ROUTER_API_KEY="isolated-gateway-secret", API_SERVER_KEY="isolated-runtime-secret")
    values[missing] = ""
    result = run_launcher(launcher_tree, name, launcher_env(**values), "-CheckOnly")
    assert result.returncode != 0
    assert "Centralized settings" in result.stderr
    for secret in (values["ARYN_9ROUTER_API_KEY"], values["API_SERVER_KEY"]):
        assert secret not in result.stdout + result.stderr
    assert not (launcher_tree / ".local").exists()


@pytest.mark.parametrize("environment", ["development", "production"])
def test_studio_check_only_accepts_explicit_overrides_without_secret_output(launcher_tree, environment):
    result = run_launcher(launcher_tree, "start-studio.ps1", launcher_env(
        ARYN_ENV=environment, ARYN_STUDIO_HOST="localhost", ARYN_STUDIO_PORT="8715",
        ARYN_RUNTIME_BASE_URL="http://127.0.0.1:8645", ARYN_9ROUTER_BASE_URL="http://127.0.0.1:20129/v1",
        ARYN_9ROUTER_API_KEY="isolated-gateway-secret", API_SERVER_KEY="isolated-runtime-secret"), "-CheckOnly")
    assert result.returncode == 0, result.stderr
    assert "Konfigurasi Studio valid" in result.stdout
    assert "secret" not in result.stdout + result.stderr
    assert not (launcher_tree / ".local").exists()


def test_configuration_helper_exports_centralized_defaults_and_override_values(launcher_tree):
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("Windows PowerShell is not installed")
    script = launcher_tree / "scripts" / "inspect.ps1"
    script.write_text(
        ". (Join-Path $PSScriptRoot 'aryn-config.ps1')\n"
        "Initialize-ArynConfiguration -Root (Split-Path $PSScriptRoot -Parent)\n"
        "@{runtime=$env:ARYN_RUNTIME_BASE_URL; gateway=$env:ARYN_9ROUTER_BASE_URL; "
        "host=$env:ARYN_STUDIO_HOST; port=$env:ARYN_STUDIO_PORT} | ConvertTo-Json", encoding="utf-8")
    result = run_launcher(launcher_tree, "inspect.ps1", launcher_env())
    assert result.returncode == 0, result.stderr
    from packages.config import ARYNSettings
    defaults = ARYNSettings()
    assert json.loads(result.stdout) == {"runtime": defaults.runtime_base_url,
        "gateway": defaults.nine_router_base_url, "host": defaults.studio_host, "port": str(defaults.studio_port)}
    result = run_launcher(launcher_tree, "inspect.ps1", launcher_env(
        ARYN_RUNTIME_BASE_URL="http://localhost:8648", ARYN_9ROUTER_BASE_URL="http://localhost:20130/v1"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["runtime"] == "http://localhost:8648"
    assert json.loads(result.stdout)["gateway"] == "http://localhost:20130/v1"
