from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    Do NOT wrap defaults in os.getenv()... that bypasses Pydantics loading mechanism apperntly
    """

    # Postgres
    POSTGRES_SERVER: str = "postgres.postgres.svc.cluster.local"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "db_lord"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""

    # Influx
    INFLUX_URL: str = "http://influxdb-service.influx.svc.cluster.local:8086"
    INFLUX_ORG: str = "my-org"
    INFLUX_BUCKET: str = "medical_data"
    INFLUX_TOKEN: str = ""
    INFLUX_ENABLE_GZIP: bool = True
    INFLUX_TIMEOUT_MS: int | None = None
    INFLUX_CONNECTION_POOL_MAXSIZE: int | None = None
    INFLUX_SCHEMA_CACHE_TTL_SECONDS: int = 300
    INFLUX_SCHEMA_CACHE_MAX_MEASUREMENTS: int = 1000
    INFLUX_SCHEMA_LOOKBACK: int = 0

    # SQLAlchemy pool tuning
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    GRAPHQL_DB_MAX_CONCURRENCY: int = 8
    TELEMETRY_MAX_IDS_PER_TAG: int = 5000
    TELEMETRY_MAX_TOTAL_IDS: int = 20000

    ERRORS_INCLUDE_TECHNICAL_DETAILS: bool = False

    @property
    def POSTGRES_URL(self) -> URL:
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=int(self.POSTGRES_PORT),
            database=self.POSTGRES_DB,
        )
        return url

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")


settings = Settings()
