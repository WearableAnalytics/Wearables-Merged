import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORKER_")

    dsn: str = "postgresql://worker:worker@localhost:55433/worker"
    id: str = socket.gethostname()
    poll_interval_seconds: float = 2.0
    batch_size: int = 8  # candidates per claim = rows per LOTUS call (plan §1, provisional)
    lease_seconds: int = 900  # must cover a whole batch: 8 x (triage + explain) on a slow model
    max_attempts: int = 3
    backoff_seconds: float = 5.0

    # Any OpenAI-compatible endpoint: local Ollama, the cluster model, or `python -m llm_worker fake-llm`.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b"
    llm_api_key: str = "unused"
    llm_timeout_seconds: float = 180.0
    llm_concurrency: int = 4  # parallel calls inside one LOTUS batch

    scenarios_dir: str | None = None  # mock data; default: the scenarios bundled in llm_worker/scenarios
