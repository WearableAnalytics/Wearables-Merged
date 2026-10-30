"""Bounded runtime configuration. Secrets have no development defaults."""

import base64
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache


def env(name, default=""):
    return field(default_factory=lambda: os.getenv(name, default), repr=False)


@dataclass
class Settings:
    kafka_bootstrap_servers: str = env("KAFKA_BOOTSTRAP_SERVERS", "kafka-kafka-bootstrap:9092")
    kafka_topic: str = env("KAFKA_TOPIC", "wearables-raw")
    kafka_results_topic: str = env("KAFKA_RESULTS_TOPIC", "wearables-ingestion-results")
    kafka_results_group: str = env("KAFKA_RESULTS_GROUP", "reliable-ingestion-results-v1")
    kafka_output_topic: str = env("KAFKA_OUTPUT_TOPIC", "wearables-lp")
    kafka_client_id: str = env("KAFKA_CLIENT_ID", "import-service")
    kafka_security_json: str = env("KAFKA_SECURITY_JSON", "{}")
    jwt_secret: str = env("JWT_SECRET")
    registration_issuer: str = env("JWT_ISSUER", "registration-service")
    database_url: str = env("INGEST_DATABASE_URL")
    archive_key_b64: str = env("INGEST_ARCHIVE_KEY")
    signing_key_b64: str = env("INGEST_SIGNING_KEY")
    archive_key_id: str = env("INGEST_ARCHIVE_KEY_ID", "initial")
    archive_old_keys_json: str = env("INGEST_ARCHIVE_OLD_KEYS", "{}")
    max_body_bytes: int = field(default_factory=lambda: int(os.getenv("INGEST_MAX_BODY_BYTES", "500000")))
    max_readings: int = field(default_factory=lambda: int(os.getenv("INGEST_MAX_READINGS", "1000")))
    max_inflight: int = field(default_factory=lambda: int(os.getenv("INGEST_MAX_INFLIGHT", "16")))
    delivery_timeout_ms: int = field(default_factory=lambda: int(os.getenv("KAFKA_DELIVERY_TIMEOUT_MS", "10000")))
    lease_seconds: int = 60
    replay_seconds: int = 300
    max_attempts: int = 12
    influxdb_url: str = env("INFLUXDB_URL", "http://localhost:8086")
    influxdb_token: str = env("INFLUXDB_TOKEN")
    influxdb_org: str = env("INFLUXDB_ORG", "test")
    influxdb_bucket: str = env("INFLUXDB_BUCKET", "gmstest")

    @staticmethod
    def decode_key(value):
        try:
            key = base64.b64decode(value, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Ingestion keys must be base64-encoded 32-byte keys") from exc
        if len(key) != 32:
            raise ValueError("Ingestion keys must be base64-encoded 32-byte keys")
        return key

    def validate(self):
        if not self.database_url or len(self.jwt_secret) < 32:
            raise ValueError("INGEST_DATABASE_URL and a JWT_SECRET of at least 32 characters are required")
        if not 1 <= self.max_body_bytes <= 700_000 or not 1 <= self.max_readings <= 10_000:
            raise ValueError("Invalid ingestion body or reading limit")
        if not 1 <= self.max_inflight <= 256 or not 100 <= self.delivery_timeout_ms <= 30_000:
            raise ValueError("Invalid ingestion concurrency or delivery timeout")
        if not self.archive_key_id or len(self.archive_key_id) > 64:
            raise ValueError("Invalid archive key identifier")
        self.decode_key(self.archive_key_b64)
        self.decode_key(self.signing_key_b64)
        if self.archive_key_b64 == self.signing_key_b64:
            raise ValueError("Archive and signing keys must be different")
        for key in json.loads(self.archive_old_keys_json).values():
            self.decode_key(key)
        allowed = {
            "security.protocol",
            "ssl.ca.location",
            "ssl.certificate.location",
            "ssl.key.location",
            "ssl.key.password",
            "sasl.mechanism",
            "sasl.username",
            "sasl.password",
        }
        if set(json.loads(self.kafka_security_json)) - allowed:
            raise ValueError("KAFKA_SECURITY_JSON contains unsupported settings")


@lru_cache
def get_settings():
    return Settings()
