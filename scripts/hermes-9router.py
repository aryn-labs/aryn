"""Bootstrap using the installed Hermes interpreter, without modifying its installation."""
import argparse
import os
from pathlib import Path
import runpy
import sys

# Do not make inherited provider credentials available to Hermes integrations.
# Remove by variable name only; values are neither read nor copied.
for credential_name in list(os.environ):
    if credential_name.endswith("_API_KEY") and credential_name != "ARYN_9ROUTER_API_KEY":
        del os.environ[credential_name]

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--hermes-source", required=True)
args, _ = parser.parse_known_args()
source = Path(args.hermes_source).resolve()
if not (source / "run_agent.py").is_file():
    raise SystemExit("Installed Hermes source not found.")
sys.path.insert(0, str(source))
from hermes_constants import get_default_hermes_root
os.environ.setdefault("HERMES_HOME", str(get_default_hermes_root()))
import hermes_bootstrap  # noqa: F401 — installed dependency environment
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runpy.run_module("services.runtime.hermes_9router", run_name="__main__")
