import os
from functools import lru_cache
from dataclasses import dataclass


@dataclass
class Settings:
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-kafka-bootstrap:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "wearables-raw")
    kafka_client_id: str = os.getenv("KAFKA_CLIENT_ID", "import-service")
    kafka_linger_ms: int = int(os.getenv("KAFKA_LINGER_MS", "50"))
    kafka_batch_size: int = int(os.getenv("KAFKA_BATCH_SIZE", "65536")) 
    kafka_buffer_memory: int = int(os.getenv("KAFKA_BUFFER_MEMORY", "33554432"))
    
    # InfluxDB
    influxdb_url: str = os.getenv("INFLUXDB_URL", "http://localhost:8086")
    influxdb_token: str = os.getenv("INFLUXDB_TOKEN", "")
    influxdb_org: str = os.getenv("INFLUXDB_ORG", "test")
    influxdb_bucket: str = os.getenv("INFLUXDB_BUCKET", "gmstest")

    jwt_secret: str = os.getenv("JWT_SECRET") or (_ for _ in ()).throw(
        ValueError("JWT_SECRET environment variable must be set – refusing to start with insecure default")
    )
    registration_issuer: str = os.getenv("JWT_ISSUER", "registration-service")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
