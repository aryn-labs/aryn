"""Create a review artifact from an explicit allowlist, bound to the tested SHA.

The wheel is the Python application library, not a VPS installer. Static Studio,
migrations/config and frozen dependency descriptions accompany it for infra review.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def build():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip())
    if os.getenv("GITHUB_SHA") and os.environ["GITHUB_SHA"] != sha:
        raise RuntimeError("Delivery must match the workflow's exact tested commit.")
    if os.getenv("GITHUB_SHA") and dirty:
        raise RuntimeError("CI delivery cannot contain modified source.")
    output = Path(".local/delivery")
    output.mkdir(parents=True, exist_ok=False)
    wheels = output / "python"
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels)], check=True)
    wheel, = wheels.glob("*.whl")
    with zipfile.ZipFile(wheel) as bundle:
        names = bundle.namelist()
        assert "modules/core/workflows/coordinator.py" in names
        assert "database/migrations/versions/015_authentication_boundary.py" in names
        assert all(name in names for name in (
            "packages/contracts/intelligence.py", "modules/brief/service.py",
            "modules/relay/service.py", "modules/relay/recovery.py", "modules/bench/replay.py",
            "services/api/intelligence.py", "database/migrations/versions/019_intelligence_recovery.py"))
        assert all(name.endswith((".py", "METADATA", "WHEEL", "top_level.txt", "RECORD")) for name in names), "Unexpected wheel data."
        # Namespace packages require real extracted directories (zipimport cannot
        # resolve every implicit namespace). Verify the delivered wheel's files,
        # never an editable source import; keep verification data out of delivery.
        verified = Path(".local/wheel-verification")
        verified.mkdir(parents=True, exist_ok=False)
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in names)
        bundle.extractall(verified)
        script = "import sys; sys.path.insert(0, sys.argv[1]); import modules.core.workflows.coordinator as c; assert c.__file__.startswith(sys.argv[1]); import services.api.authentication; import services.api.intelligence; import modules.brief.service; import modules.relay.recovery; import modules.bench.replay; print('BUILT_WHEEL_IMPORT_PASS')"
        subprocess.run([sys.executable, "-I", "-c", script, str(verified.resolve())], check=True)
    shutil.copytree("apps/web/dist", output / "web")
    for filename in ("pyproject.toml", "uv.lock", "alembic.ini", "README.md", "apps/web/package-lock.json"):
        shutil.copyfile(filename, output / Path(filename).name)
    protected = [value.encode() for name, value in os.environ.items()
                 if name.startswith(("ARYN_", "API_SERVER_")) and any(part in name for part in ("SECRET", "KEY")) and len(value) >= 16]
    entries = []
    for path in output.rglob("*"):
        if path.is_file():
            assert path.suffix not in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".log"}
            data = path.read_bytes()
            assert not any(value in data for value in protected), "Protected environment material found in artifact."
            if path.suffix == ".whl":
                with zipfile.ZipFile(path) as bundle:
                    assert not any(value in bundle.read(name) for name in bundle.namelist() for value in protected)
            entries.append({"path": path.relative_to(output).as_posix(), "sha256": hashlib.sha256(data).hexdigest()})
    metadata = {"commit": sha, "source_modified": dirty, "workflow_run": os.getenv("GITHUB_RUN_ID"), "workflow_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
                "repository": "aryn-labs/aryn", "python": sys.version.split()[0], "files_sha256": entries,
                "dependency_sources": ["uv.lock", "package-lock.json"], "deployment": "review-only; no production deployment"}
    (output / "build-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Safe delivery artifact bound to {sha}")


if __name__ == "__main__":
    build()
