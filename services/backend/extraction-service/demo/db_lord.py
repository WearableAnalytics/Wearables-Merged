"""Synthetic db_lord HTTP endpoint used only by the monitoring demo."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class DemoDbLord(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/telemetry/stream":
            self.send_error(404)
            return
        measurement = parse_qs(url.query).get("measurement", [None])[0]
        if measurement == "demo-upstream-failure":
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for index, kind in enumerate(("steps", "demo-unsupported", "steps")):
            if measurement and measurement != kind:
                continue
            point = {
                "measurement": kind,
                "timestamp": f"2026-01-01T12:0{3-index}:00Z",
                "tags": {"device-id": "synthetic-demo"},
                "fields": {"value": 10 + index},
            }
            self.wfile.write((json.dumps(point) + "\n").encode())


if __name__ == "__main__":
    with ThreadingHTTPServer(("0.0.0.0", 8080), DemoDbLord) as server:
        server.serve_forever()
