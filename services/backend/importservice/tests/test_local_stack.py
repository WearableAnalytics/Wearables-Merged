"""Local configuration must satisfy the combined services without public defaults."""

import base64
import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def helpers(monkeypatch):
    modules = []
    for name, filename in (("init_env", "init_env.py"), ("local_login_link", "login_link.py")):
        spec = importlib.util.spec_from_file_location(name, ROOT / "deploy/local" / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def test_local_keys_are_private_distinct_and_retained_on_reconfiguration(helpers, tmp_path):
    local, _ = helpers
    path = tmp_path / ".env"
    local.configure(path)
    first = local.read_env(path)
    local.configure(path)
    assert local.read_env(path) == first
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert first["INGEST_ARCHIVE_KEY"] != first["INGEST_SIGNING_KEY"]
    assert len(base64.b64decode(first["INGEST_ARCHIVE_KEY"])) == 32
    assert len(first["JWT_SECRET"]) >= 32
    tokens = [first[name] for name in ("CONTROL_WRITE_TOKEN", "API_TOKEN_SERVICE_TOKEN", "DATABASE_OPERATOR_TOKEN")]
    assert len(set(tokens)) == 3
    assert urlsplit(first["INGEST_DATABASE_URL"]).username == "wearables_ingest"
    assert urlsplit(first["INGEST_MIGRATION_DATABASE_URL"]).username == "wearables_migrate"


def test_local_compose_connects_runtime_authority_and_pipeline_without_public_bindings(helpers, tmp_path):
    local, _ = helpers
    path = tmp_path / ".env"
    local.configure(path)
    process = subprocess.run(
        ["docker", "compose", "--env-file", str(path), "-f", str(ROOT / "deploy/local/docker-compose.yml"),
         "config", "--format", "json"], capture_output=True, text=True, check=False,
    )
    assert process.returncode == 0, process.stderr
    services = json.loads(process.stdout)["services"]
    importer = services["importservice"]["environment"]
    mapper = services["fhir-mapper-validator"]["environment"]
    migration = services["ingestion-migrate"]["environment"]
    assert importer["INGEST_DATABASE_URL"] != migration["INGEST_DATABASE_URL"]
    assert importer["INGEST_SIGNING_KEY"] == mapper["INGEST_SIGNING_KEY"]
    assert importer["INGEST_ARCHIVE_KEY"] != mapper["INGEST_SIGNING_KEY"]
    assert "INGEST_ARCHIVE_KEY" not in migration
    assert "INGEST_ARCHIVE_KEY" not in mapper
    assert "ingestion-migrate" in services["importservice"]["depends_on"]
    assert services["ingestion-migrate"]["image"] == services["importservice"]["image"]
    bff = services["wearables-bff"]["environment"]
    authority = services["db-lord"]["environment"]
    assert bff["CONTROL_WRITE_TOKEN"] == authority["CONTROL_WRITE_TOKEN"]
    assert bff["DATABASE_OPERATOR_TOKEN"] == authority["LEGACY_OPERATOR_TOKEN"]
    assert services["extraction-service"]["environment"]["DB_LORD_OPERATOR_TOKEN"] == authority["LEGACY_OPERATOR_TOKEN"]
    assert bff["ALLOW_DEV_AUTH_BYPASS"] == "false"
    for service in services.values():
        for port in service.get("ports", []):
            assert port["host_ip"] == "127.0.0.1"


def test_local_login_link_uses_stored_approval_and_hash_only(helpers):
    _, login = helpers
    received = []
    approved = True

    class Authority(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, value):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            self.reply({"items": [{"id": "synthetic-user", "auth_version": 7,
                                   "status": "approved" if approved else "pending"}], "next_cursor": None})

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.reply({"ok": True})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Authority)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        url = login.login_link({"CONTROL_WRITE_TOKEN": "synthetic-local-only"}, "admin@example.test", base,
                               "http://localhost:3001/api")
        proof = parse_qs(urlsplit(url).query)["token"][0]
        assert received == [{"token_hash": hashlib.sha256(proof.encode()).hexdigest(), "user_id": "synthetic-user",
                             "auth_version": 7, "ttl_seconds": 60}]
        approved = False
        with pytest.raises(ValueError, match="approve"):
            login.login_link({"CONTROL_WRITE_TOKEN": "synthetic-local-only"}, "pending@example.test", base,
                             "http://localhost:3001/api")
        assert len(received) == 1
        with pytest.raises(ValueError, match="loopback"):
            login.loopback_url("https://production.example.test")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
