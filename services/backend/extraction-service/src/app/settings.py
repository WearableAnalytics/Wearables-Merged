from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    db_lord_base_url: str = "http://db-lord:8000"
    db_lord_timeout_seconds: float = 120.0

    # Used when a request has no `start`. db_lord itself falls back to the last 24h, which
    # silently truncated exports, so the extraction API defaults to all data. The app uploads
    # at most 5 years of history. db_lord reads in one-day chunks from `end` back to `start`,
    # so a much earlier date would only add empty queries.
    default_start: datetime = datetime(2020, 1, 1, tzinfo=UTC)

    # Patient exports query db_lord in windows of this size (both patient tags per window).
    patient_window: timedelta = timedelta(days=30)

    # Mapping used for the FHIR export when a telemetry point carries no mapping_id tag
    # (true for all data ingested so far). Copy of the mapper-validator mapping.
    fhir_default_mapping_path: Path = Path(__file__).parent / "default_fhir_mapping.yaml"

    # Path prefix under which a reverse proxy (the BFF) serves this API, e.g. /api/extraction.
    # Makes the Swagger UI load the OpenAPI document through the proxy.
    root_path: str = ""

    # Shared with the BFF, which signs the caller (principal) it forwards with it. Without it every
    # data request is refused (503).
    extraction_internal_jwt_secret: str = ""

    # Roles that may export. The BFF sends "admin" for admins.
    export_roles: frozenset[str] = frozenset({"admin", "researcher"})

    # API tokens whose owner the BFF does not know (after a BFF restart, until the owner logs in again)
    # arrive without roles. The BFF has always accepted them; keep that unless turned off here.
    allow_unverified_token_owners: bool = True


settings = Settings()
