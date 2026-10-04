import argparse

import uvicorn

from services.api.studio import create_app

parser = argparse.ArgumentParser(description="ARYN Studio, sesi development loopback")
parser.add_argument("--port", type=int, default=8710)
args = parser.parse_args()
app = create_app(origin=f"http://127.0.0.1:{args.port}")
uvicorn.run(
    app, host="127.0.0.1", port=args.port, access_log=False, proxy_headers=False
)
