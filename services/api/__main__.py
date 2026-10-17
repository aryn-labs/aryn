import argparse

import uvicorn

from packages.config import ARYNSettings, get_settings
from services.api.authentication import AuthenticationSettings
from services.api.studio import create_app

settings = get_settings()

parser = argparse.ArgumentParser(description="ARYN Studio, sesi development loopback")
parser.add_argument("--host", type=str, default=None)
parser.add_argument("--port", type=int, default=None)
parser.add_argument("--native-worker-manifest", type=str, default=None)
args = parser.parse_args()

host = args.host or settings.studio_host
port = args.port if args.port is not None else settings.studio_port
# Command-line overrides obey the same bind validation as deployment settings.
settings = ARYNSettings(**{**settings.model_dump(), "studio_host": host, "studio_port": port})
authentication = AuthenticationSettings.from_env(settings)
origin = f"http://{host}:{port}" if authentication.mode == "local-development" else None
native_worker = None
if args.native_worker_manifest:
    import json
    from pathlib import Path
    from packages.tool_adapters.native import NativeWorker
    manifest = json.loads(Path(args.native_worker_manifest).read_text(encoding="utf-8"))
    native_worker = NativeWorker(manifest["image_id"], manifest["schemas"], toolsets=manifest.get("toolsets", {}))
app = create_app(origin=origin, authentication=authentication, native_worker=native_worker)
uvicorn.run(
    app, host=host, port=port, access_log=False, proxy_headers=False
)
