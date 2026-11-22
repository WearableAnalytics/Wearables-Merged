"""Run one API worker and one private metrics listener per container."""
import os

import uvicorn
from prometheus_client import start_http_server

from .main import app, export_metrics


def main():
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        raise RuntimeError("Run one extraction worker per pod without PROMETHEUS_MULTIPROC_DIR")
    port = int(os.getenv("METRICS_PORT", "9103"))
    if not 0 <= port <= 65535:
        raise ValueError("METRICS_PORT must be between 0 and 65535")
    if not port:
        uvicorn.run(app, host="0.0.0.0", port=8010, workers=1)
        return
    server, thread = start_http_server(port, registry=export_metrics.registry)
    try:
        uvicorn.run(app, host="0.0.0.0", port=8010, workers=1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
