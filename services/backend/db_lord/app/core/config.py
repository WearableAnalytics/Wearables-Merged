from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres
    POSTGRES_SERVER: str = "postgres.postgres.svc.cluster.local"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "db_lord"
    POSTGRES_USER: str = "postgres"
    
    POSTGRES_PASSWORD: str

    # Influx
    INFLUX_URL: str = "http://localhost:8086"
    INFLUX_ORG: str = "my-org"
    INFLUX_BUCKET: str = "medical_data"

    INFLUX_TOKEN: str

    @property
    def POSTGRES_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")


settings = Settings()
