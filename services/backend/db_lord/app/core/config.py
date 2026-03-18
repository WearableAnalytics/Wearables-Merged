import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is not set. "
            "Refusing to start with insecure defaults."
        )
    return value


class Settings(BaseSettings):
    # Postgres
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "postgres.postgres.svc.cluster.local")
    POSTGRES_PORT: int = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "db_lord")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")

    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")

    # Influx
    INFLUX_URL: str = os.getenv("INFLUX_URL", "http://influxdb-service.influx.svc.cluster.local:8086")
    INFLUX_ORG: str = os.getenv("INFLUX_ORG", "my-org")
    INFLUX_BUCKET: str = os.getenv("INFLUX_BUCKET", "medical_data")

    INFLUX_TOKEN: str = os.getenv("INFLUX_TOKEN", "")

    # Auth – crashes on startup if not set
    JWT_SECRET: str = _require_env("JWT_SECRET")

    @property
    def POSTGRES_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")


settings = Settings()
