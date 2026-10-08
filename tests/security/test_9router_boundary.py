"""Gateway boundary regressions; no live inference or provider credentials."""

import pytest
import ast
from pathlib import Path

from packages.model_adapters import ModelRouter, ModelRoutingError
from services.api.studio import runtime_key


def test_production_router_has_no_nous_default():
    router = ModelRouter()
    assert "stealth/space-bunny-alpha" not in router.catalog
    with pytest.raises(ModelRoutingError):
        router.resolve_model()


def test_runtime_auth_does_not_scan_provider_env_file(monkeypatch):
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    monkeypatch.setattr("pathlib.Path.is_file", lambda _: True)
    def forbidden_read(*args, **kwargs):
        pytest.fail("ARYN must not read a Hermes .env containing provider credentials")
    monkeypatch.setattr("pathlib.Path.read_text", forbidden_read)
    assert runtime_key() == ""


def test_production_environment_reads_are_explicit_and_never_provider_credentials():
    root = Path(__file__).resolve().parents[2]
    allowed = {
        "ARYN_ENV",
        "ARYN_STUDIO_HOST",
        "ARYN_STUDIO_PORT",
        "ARYN_RUNTIME_BASE_URL",
        "ARYN_9ROUTER_BASE_URL",
        "ARYN_9ROUTER_API_KEY",
        "API_SERVER_KEY",
        "ARYN_IDENTITY_SECRET",
        "ARYN_EVIDENCE_SECRET",
        "ARYN_HISTORY_COMMITMENT_PATH",
    }
    for directory in ("services", "packages", "modules"):
        for path in (root / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "getenv"):
                    assert node.args and isinstance(node.args[0], ast.Constant), path
                    assert node.args[0].value in allowed, path
                if isinstance(node, ast.Attribute) and node.attr == "environ":
                    pytest.fail(f"Unexpected environment enumeration/access in {path}")


def test_env_example_contains_only_safe_gateway_configuration():
    root = Path(__file__).resolve().parents[2]
    assert (root / ".env.example").read_text(encoding="utf-8").splitlines() == [
        "ARYN_ENV=development",
        "ARYN_STUDIO_HOST=127.0.0.1",
        "ARYN_STUDIO_PORT=8710",
        "ARYN_RUNTIME_BASE_URL=http://127.0.0.1:8642",
        "ARYN_9ROUTER_BASE_URL=http://127.0.0.1:20128/v1",
        "ARYN_9ROUTER_API_KEY=",
    ]
