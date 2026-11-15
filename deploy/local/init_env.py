"""Create private local configuration; retain existing data-encryption keys."""

import argparse
import base64
import os
from pathlib import Path
import re
import secrets
import shlex
import tempfile
from urllib.parse import quote


def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in values:
            raise ValueError("Invalid or repeated local configuration key")
        parsed = shlex.split(value, comments=True)
        values[key] = parsed[0] if parsed else ""
    return values


def configure(path):
    if path.is_symlink():
        raise ValueError("Refusing a symlink for the local secret file")
    template = Path(__file__).with_name(".env.example")
    text = path.read_text() if path.exists() else template.read_text()
    values = read_env(path if path.exists() else template)
    if values.get("JWT_SECRET") == "dev-secret":
        values["JWT_SECRET"] = ""
    for key in ("JWT_SECRET", "CONTROL_WRITE_TOKEN", "API_TOKEN_SERVICE_TOKEN", "DATABASE_OPERATOR_TOKEN",
                "INGEST_RUNTIME_PASSWORD", "INGEST_MIGRATION_PASSWORD", "POSTGRES_PASSWORD",
                "INFLUX_TOKEN", "INFLUX_PASSWORD", "GRAFANA_ADMIN_PASSWORD"):
        if not values.get(key):
            values[key] = secrets.token_hex(32)
    for key in ("INGEST_ARCHIVE_KEY", "INGEST_SIGNING_KEY"):
        if not values.get(key):
            values[key] = base64.b64encode(secrets.token_bytes(32)).decode()
        if len(base64.b64decode(values[key], validate=True)) != 32:
            raise ValueError(f"{key} must encode exactly 32 bytes; existing keys are never replaced")
    if values["INGEST_ARCHIVE_KEY"] == values["INGEST_SIGNING_KEY"]:
        raise ValueError("Archive and signing keys must differ")
    authority_keys = [values[name] for name in
                      ("JWT_SECRET", "CONTROL_WRITE_TOKEN", "API_TOKEN_SERVICE_TOKEN", "DATABASE_OPERATOR_TOKEN")]
    if any(len(value) < 32 for value in authority_keys) or len(set(authority_keys)) != len(authority_keys):
        raise ValueError("Use distinct account credentials with at least 32 characters")
    if values["INGEST_RUNTIME_PASSWORD"] == values["INGEST_MIGRATION_PASSWORD"]:
        raise ValueError("Ingestion runtime and migration passwords must differ")
    values.setdefault("ADMIN_EMAILS", "admin@example.test")
    if not values.get("INGEST_DATABASE_URL"):
        values["INGEST_DATABASE_URL"] = (
            "postgresql://wearables_ingest:" + quote(values["INGEST_RUNTIME_PASSWORD"], safe="")
            + "@postgres:5432/wearables_ingestion"
        )
    if not values.get("INGEST_MIGRATION_DATABASE_URL"):
        values["INGEST_MIGRATION_DATABASE_URL"] = (
            "postgresql://wearables_migrate:" + quote(values["INGEST_MIGRATION_PASSWORD"], safe="")
            + "@postgres:5432/wearables_ingestion"
        )
    for key, value in values.items():
        replacement = f"{key}={shlex.quote(value)}"
        pattern = re.compile(r"^" + re.escape(key) + r"=.*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda _match: replacement, text)
        else:
            text += "\n" + replacement + "\n"
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".local-env-", delete=False) as output:
        temporary = Path(output.name)
        try:
            os.chmod(temporary, 0o600)
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env"))
    args = parser.parse_args()
    configure(args.env_file)
    print("Local configuration is ready. Existing credentials and archive keys were retained.")
