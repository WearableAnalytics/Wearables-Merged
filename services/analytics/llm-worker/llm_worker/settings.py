import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORKER_")

    dsn: str = "postgresql://worker:worker@localhost:55433/worker"
    id: str = socket.gethostname()
    work_seconds: float = 10.0
    poll_interval_seconds: float = 2.0
    lease_seconds: int = 60
    max_attempts: int = 3
    backoff_seconds: float = 5.0
