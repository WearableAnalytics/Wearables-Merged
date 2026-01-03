import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Settings:
    postgres_user: str = os.getenv("POSTGRES_USER", "user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "password")
    postgres_db: str = os.getenv("POSTGRES_DB", "db")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://admin:admin-password@postgres.postgres.svc.cluster.local:5432/db"
    )

    influx_url: str = os.getenv("INFLUX_URL", "http://influxdb-service.influx.svc.cluster.local:8086")
    influx_token: str = os.getenv("INFLUX_TOKEN", "token")
    influx_org: str = os.getenv("INFLUX_ORG", "test")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "test")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
