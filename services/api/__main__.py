import argparse

import uvicorn

from packages.config import get_settings
from services.api.studio import create_app

settings = get_settings()

parser = argparse.ArgumentParser(description="ARYN Studio, sesi development loopback")
parser.add_argument("--host", type=str, default=None)
parser.add_argument("--port", type=int, default=None)
args = parser.parse_args()

host = args.host or settings.studio_host
port = args.port if args.port is not None else settings.studio_port
origin = f"http://{host}:{port}"
app = create_app(origin=origin)
uvicorn.run(
    app, host=host, port=port, access_log=False, proxy_headers=False
)
