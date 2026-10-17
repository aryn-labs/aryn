"""Hermes receives neither ambient credentials nor the user's native state home."""
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("unsafe_home", [False, True])
def test_runtime_environment_and_home_are_explicitly_isolated(tmp_path, monkeypatch, unsafe_home):
    source = tmp_path / "installed-source"
    source.mkdir()
    (source / "run_agent.py").write_text("", encoding="utf-8")
    global_home = tmp_path / "user-state"
    scoped_home = global_home if unsafe_home else tmp_path / "aryn-state"
    environment = {"PATH": "os-bootstrap-path", "API_SERVER_KEY": "runtime-only-secret",
        "ARYN_9ROUTER_API_KEY": "gateway-only-secret", "ARYN_IDENTITY_SECRET": "core-only-secret",
        "ARYN_EVIDENCE_SECRET": "core-evidence-secret", "GH_TOKEN": "provider-oauth",
        "ANTHROPIC_API_KEY": "provider-key", "SSH_AUTH_SOCK": "agent-socket"}
    monkeypatch.setattr(os, "environ", environment)
    monkeypatch.setattr(sys, "path", list(sys.path))
    pins = []
    monkeypatch.setitem(sys.modules, "hermes_constants", SimpleNamespace(get_default_hermes_root=lambda: global_home,
        set_hermes_home_override=lambda value: pins.append(value), pin_process_hermes_home=lambda value: pins.append(value)))
    monkeypatch.setitem(sys.modules, "hermes_bootstrap", SimpleNamespace())
    (tmp_path / "existing-venv/site-packages").mkdir(parents=True)
    dependencies = SimpleNamespace(selected_venv=lambda root: tmp_path / "existing-venv",
        site_packages=lambda root: root / "site-packages", activate_dependencies=lambda root: pytest.fail("Mutable activation invoked"))
    recovery = SimpleNamespace(interrupted_pull_marker=lambda root: root / ".git/hermes-update-pull",
        restore_interrupted_pull=lambda *args, **kwargs: pytest.fail("Native update invoked"),
        recover_if_needed=lambda *args, **kwargs: pytest.fail("Native recovery invoked"))
    launch = SimpleNamespace(completion_pending_path=lambda root: root / "completion-pending",
        prepare_launch=lambda *args, **kwargs: pytest.fail("Native install invoked"))
    monkeypatch.setitem(sys.modules, "pm.environments", dependencies)
    monkeypatch.setitem(sys.modules, "hermes_cli._early_recovery", recovery)
    monkeypatch.setitem(sys.modules, "hermes_cli.venv_sync", launch)
    dispatched = []
    monkeypatch.setattr(runpy, "run_module", lambda *args, **kwargs: dispatched.append(args))
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--hermes-source", str(source), "--runtime-home", str(scoped_home)])
    script = Path(__file__).resolve().parents[2] / "scripts/hermes-9router.py"
    if unsafe_home:
        with pytest.raises(SystemExit):
            runpy.run_path(str(script), run_name="__main__")
        assert not global_home.exists() and not dispatched
        from services.runtime.bootstrap import prepare_runtime_home
        with pytest.raises(SystemExit):
            prepare_runtime_home(source, tmp_path, environment)
        assert not (tmp_path / "config.yaml").exists()
    else:
        runpy.run_path(str(script), run_name="__main__")
        assert pins == [str(scoped_home)] * 2
        assert environment["HERMES_HOME"] == str(scoped_home)
        assert (scoped_home / "config.yaml").exists()
        assert dispatched
        dependencies.activate_dependencies(source)
        assert recovery.restore_interrupted_pull() is False
        assert recovery.recover_if_needed() is False
        assert launch.prepare_launch(source, []) is None
        assert environment["HERMES_DISABLE_LAZY_INSTALLS"] == "1"
        marker = source / "completion-pending"
        marker.write_text("operator repair required", encoding="utf-8")
        from services.runtime.bootstrap import prepare_runtime_home
        with pytest.raises(SystemExit, match="operator repair"):
            prepare_runtime_home(source, tmp_path / "refused-home", environment)
        assert marker.exists() and not (tmp_path / "refused-home").exists()
        marker.unlink()
        (tmp_path / "existing-venv/site-packages").rmdir()
        with monkeypatch.context() as standalone:
            standalone.setattr(sys, "prefix", "explicit-standalone")
            standalone.setattr(sys, "base_prefix", "explicit-standalone")
            with pytest.raises(SystemExit, match="dependency generation is unavailable"):
                prepare_runtime_home(source, tmp_path / "missing-dependencies", environment)
        assert not (tmp_path / "missing-dependencies").exists()
    assert not {"ARYN_IDENTITY_SECRET", "ARYN_EVIDENCE_SECRET", "GH_TOKEN", "ANTHROPIC_API_KEY", "SSH_AUTH_SOCK"} & environment.keys()
    assert environment["API_SERVER_KEY"] == "runtime-only-secret"
    assert environment["ARYN_9ROUTER_API_KEY"] == "gateway-only-secret"
