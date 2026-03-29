from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    Do NOT wrap defaults in os.getenv()... that bypasses Pydantics loading mechanism apperntly.
    All of these setting are pretty random and arbitrary right now. For real deployment they should be adjusted!
    """

    # Postgres
    POSTGRES_SERVER: str = "postgres.postgres.svc.cluster.local"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "db_lord"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1_800
    DB_POOL_PRE_PING: bool = True
    DB_POOL_WARN_THRESHOLD: int = 80

    # Influx
    INFLUX_URL: str = "http://influxdb-service.influx.svc.cluster.local:8086"
    INFLUX_ORG: str = "my-org"
    INFLUX_BUCKET: str = "medical_data"
    INFLUX_TOKEN: str = ""
    INFLUX_ENABLE_GZIP: bool = True
    INFLUX_TIMEOUT_MS: int | None = 60_000
    INFLUX_CONNECTION_POOL_MAXSIZE: int | None = None
    INFLUX_SCHEMA_CACHE_TTL_SECONDS: int = 300
    INFLUX_SCHEMA_CACHE_MAX_MEASUREMENTS: int = 1_000
    INFLUX_SCHEMA_LOOKBACK: int = 0
    INFLUX_STRUCTURED_READ_INITIAL_WINDOW_SECONDS: int = 3_600
    INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS: int = 86_400
    INFLUX_STRUCTURED_READ_WINDOW_GROWTH_FACTOR: float = 4.0

    # Runtime / concurrency
    WEB_CONCURRENCY: int = 4
    GRAPHQL_DB_MAX_CONCURRENCY: int = 8
    GRAPHQL_DATALOADER_MAX_BATCH_SIZE: int = 500
    GRAPHQL_WS_KEEP_ALIVE_INTERVAL_SECONDS: int = 15
    GRAPHQL_RELAY_MAX_RESULTS: int = 100
    GRAPHQL_MAX_DEPTH: int = 12
    GRAPHQL_MAX_TOKENS: int = 5_000
    GRAPHQL_MAX_ALIASES: int = 15

    # Health
    HEALTHCHECK_DB_TIMEOUT_MS: int = 5_000
    HEALTHCHECK_INFLUX_TIMEOUT_MS: int = 5_000

    # Telemetry GraphQL fanout guards
    TELEMETRY_MAX_IDS_PER_TAG: int = 5_000
    TELEMETRY_MAX_TOTAL_IDS: int = 20_000

    # Misc
    ERRORS_INCLUDE_TECHNICAL_DETAILS: bool = False
    ENVIRONMENT: str = "development"

    @property
    def POSTGRES_URL(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=int(self.POSTGRES_PORT),
            database=self.POSTGRES_DB,
        )

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")


settings = Settings()
