"""Bootstrap using the installed Hermes interpreter, without modifying its installation."""
import argparse
import os
from pathlib import Path
import runpy
import sys

# Retain only OS bootstrap paths and the explicitly configured ARYN boundary.
# Provider OAuth tokens, SSH agents and Core signing/database credentials never
# enter the runtime environment. Inspect names only, never copy their values.
runtime_environment = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "TZ",
    "ARYN_ENV", "ARYN_STUDIO_HOST", "ARYN_STUDIO_PORT", "ARYN_RUNTIME_BASE_URL",
    "ARYN_9ROUTER_BASE_URL", "ARYN_9ROUTER_API_KEY", "API_SERVER_KEY"}
for credential_name in list(os.environ):
    if credential_name not in runtime_environment and not credential_name.startswith("LC_"):
        del os.environ[credential_name]

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--hermes-source", required=True)
parser.add_argument("--runtime-home", default=str(Path(__file__).resolve().parents[1] / ".local/hermes-runtime"))
args, _ = parser.parse_known_args()
source = Path(args.hermes_source).resolve()
if not (source / "run_agent.py").is_file():
    raise SystemExit("Installed Hermes source not found.")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.runtime.bootstrap import prepare_runtime_home
prepare_runtime_home(source, args.runtime_home, os.environ)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runpy.run_module("services.runtime.hermes_9router", run_name="__main__")
