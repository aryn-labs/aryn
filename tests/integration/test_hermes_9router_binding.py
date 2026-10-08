"""Optional installed-runtime check uses isolated HOME/config and HTTP doubles only."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

import pytest


def test_installed_hermes_executes_via_guarded_gateway_double(tmp_path):
    configured = os.getenv("ARYN_TEST_HERMES_SOURCE")
    if configured:
        source = Path(configured)
        runtime = os.environ["ARYN_TEST_HERMES_PYTHON"]
        assert source.is_dir() and Path(runtime).is_file(), "Configured native Hermes verification must not skip."
    else:
        command = shutil.which("hermes.exe")
        source = Path.home() / "AppData/Local/hermes/hermes-agent"
        if not command or not source.is_dir():
            pytest.skip("Installed Hermes interpreter not available; dedicated native CI verification is mandatory.")
        runtime = json.loads(subprocess.check_output([command, "--print-runtime-command"], text=True))[0]
    home = tmp_path / "hermes-isolated"
    home.mkdir()
    (home / "config.yaml").write_text("platform_toolsets:\n  api_server: []\nmemory:\n  memory_enabled: false\ncompression:\n  enabled: false\n", encoding="utf-8")
    env = {k: os.environ[k] for k in ("SystemRoot", "PATH", "HOME", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "TEMP", "TMP") if k in os.environ}
    key = secrets.token_hex(32)
    env.update(HERMES_HOME=str(source.parent), ARYN_TEST_HERMES_HOME=str(home), API_SERVER_KEY=key)
    root = Path(__file__).resolve().parents[2]
    stdout, stderr = tmp_path / "stdout.txt", tmp_path / "stderr.txt"
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        process = subprocess.Popen([runtime, "-u", "-I", str(root / "tests/hermes_gateway_check.py"), str(source)],
                                   cwd=root, env=env, stdout=out, stderr=err)
        try:
            process.wait(timeout=35)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    output = stdout.read_text(encoding="utf-8", errors="replace")
    errors = stderr.read_text(encoding="utf-8", errors="replace")
    assert key not in output + errors
    assert "isolated-gateway-native-auth" not in output + errors
    assert process.returncode == 0, (output[-1500:], errors[-2000:])
    assert "REAL_HERMES_ISOLATED_GATEWAY_PASS" in output
    assert "REAL_HERMES_CONFINED_ROUTES_PASS" in output
