"""Launcher wiring only; never starts services or performs model inference."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("runtime_fails", [False, True])
def test_combined_launcher_shares_ephemeral_auth_and_stops_on_runtime_failure(tmp_path, runtime_fails):
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("Windows PowerShell is not installed")
    source = Path(__file__).resolve().parents[2] / "scripts" / "start-aryn.ps1"
    shutil.copyfile(source, tmp_path / source.name)
    (tmp_path / "start-runtime-9router.ps1").write_text(
        "throw 'isolated runtime failure'" if runtime_fails else
        "$env:API_SERVER_KEY = [guid]::NewGuid().ToString('N')\n"
        "$env:ARYN_LAUNCH_TEST_AUTH = $env:API_SERVER_KEY\n"
        "Write-Output 'isolated runtime ready'",
        encoding="utf-8",
    )
    (tmp_path / "start-studio.ps1").write_text(
        "param([switch]$NoBrowser, [switch]$SkipInstall, [switch]$SkipBuild)\n"
        "if (-not $env:API_SERVER_KEY -or $env:API_SERVER_KEY -ne $env:ARYN_LAUNCH_TEST_AUTH) "
        "{ throw 'runtime authentication was not inherited' }\n"
        "if (-not ($NoBrowser -and $SkipInstall -and $SkipBuild)) { throw 'flags were not forwarded' }\n"
        "Write-Output 'isolated Studio ready with shared authentication'",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tmp_path / source.name),
         "-NoBrowser", "-SkipInstall", "-SkipBuild"],
        capture_output=True, text=True, timeout=30,
    )
    if runtime_fails:
        assert result.returncode != 0
        assert "Studio ready" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "Studio ready with shared authentication" in result.stdout
