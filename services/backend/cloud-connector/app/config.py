import os
from functools import lru_cache
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    app_name: str = "Wearables Cloud Connector"
    kafka_bootstrap_servers: str = field(
        default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    )
    kafka_topic: str = field(default_factory=lambda: os.getenv("KAFKA_TOPIC", "wearables-raw"))
    kafka_client_id: str = field(
        default_factory=lambda: os.getenv("KAFKA_CLIENT_ID", "wearables-cloud-connector")
    )
    kafka_connect_retries: int = field(
        default_factory=lambda: int(os.getenv("KAFKA_CONNECT_RETRIES", "5"))
    )
    kafka_connect_backoff: float = field(
        default_factory=lambda: float(os.getenv("KAFKA_CONNECT_BACKOFF", "1.0"))
    )
    storage_path: str = field(
        default_factory=lambda: os.getenv("CLOUD_CONNECTOR_STORAGE_PATH", "/data/connections.json")
    )
    outbox_dir: str = field(
        default_factory=lambda: os.getenv("CLOUD_CONNECTOR_OUTBOX_DIR", "").strip()
    )
    outbox_max_bytes: int = field(
        default_factory=lambda: max(
            1024, int(os.getenv("CLOUD_CONNECTOR_OUTBOX_MAX_BYTES", str(256 * 1024 * 1024)))
        )
    )
    outbox_poll_interval: float = field(
        default_factory=lambda: max(0.1, float(os.getenv("CLOUD_CONNECTOR_OUTBOX_POLL_INTERVAL", "2.0")))
    )
    outbox_max_backoff: float = field(
        default_factory=lambda: max(1.0, float(os.getenv("CLOUD_CONNECTOR_OUTBOX_MAX_BACKOFF", "30.0")))
    )

    # Central public base URL for all OAuth callbacks
    public_base_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://localhost")
    )

    # Case-JWT verification
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    jwt_issuer: str = field(
        default_factory=lambda: os.getenv("JWT_ISSUER", "wearables-bff")
    )
    internal_port: int = field(
        default_factory=lambda: int(os.getenv("INTERNAL_PORT", "8001"))
    )

    # Garmin OAuth 2.0 PKCE & API settings
    garmin_client_id: str = field(default_factory=lambda: os.getenv("GARMIN_CLIENT_ID", ""))
    garmin_client_secret: str = field(
        default_factory=lambda: os.getenv("GARMIN_CLIENT_SECRET", "")
    )
    garmin_auth_url: str = field(
        default_factory=lambda: os.getenv(
            "GARMIN_AUTH_URL", "https://connect.garmin.com/oauth2Confirm"
        )
    )
    garmin_token_url: str = field(
        default_factory=lambda: os.getenv(
            "GARMIN_TOKEN_URL", "https://diauth.garmin.com/di-oauth2-service/oauth/token"
        )
    )
    garmin_partner_gateway_url: str = field(
        default_factory=lambda: os.getenv(
            "GARMIN_PARTNER_GATEWAY_URL", "https://apis.garmin.com/partner-gateway/rest"
        )
    )
    garmin_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GARMIN_API_BASE_URL", "https://apis.garmin.com/wellness-api/rest"
        )
    )
    garmin_environment: str = field(
        default_factory=lambda: os.getenv("GARMIN_ENVIRONMENT", "evaluation").strip().lower()
    )
    garmin_backfill_enabled: bool = field(
        default_factory=lambda: _env_bool("GARMIN_BACKFILL_ENABLED", False)
    )
    garmin_allow_pre_auth_history: bool = field(
        default_factory=lambda: _env_bool("GARMIN_ALLOW_PRE_AUTH_HISTORY", False)
    )
    garmin_verify_client_id: bool = field(
        default_factory=lambda: _env_bool("GARMIN_VERIFY_CLIENT_ID", False)
    )
    garmin_backfill_chunk_days: int = field(
        default_factory=lambda: max(1, min(30, int(os.getenv("GARMIN_BACKFILL_CHUNK_DAYS", "7"))))
    )
    garmin_backfill_delay_seconds: float = field(
        default_factory=lambda: max(0.0, float(os.getenv("GARMIN_BACKFILL_DELAY_SECONDS", "0.5")))
    )
    garmin_sync_max_attempts: int = field(
        default_factory=lambda: max(1, int(os.getenv("GARMIN_SYNC_MAX_ATTEMPTS", "3")))
    )

    # Polar AccesLink OAuth 2.0 & API settings
    polar_client_id: str = field(default_factory=lambda: os.getenv("POLAR_CLIENT_ID", ""))
    polar_client_secret: str = field(
        default_factory=lambda: os.getenv("POLAR_CLIENT_SECRET", "")
    )
    polar_auth_url: str = field(
        default_factory=lambda: os.getenv(
            "POLAR_AUTH_URL", "https://flow.polar.com/oauth2/authorization"
        )
    )
    polar_token_url: str = field(
        default_factory=lambda: os.getenv(
            "POLAR_TOKEN_URL", "https://polarremote.com/v2/oauth2/token"
        )
    )
    polar_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "POLAR_API_BASE_URL", "https://www.polaraccesslink.com/v3"
        )
    )

    # Google Health (Fitbit, Pixel Watch etc.) OAuth 2.0 PKCE & API settings
    google_health_client_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_HEALTH_CLIENT_ID") or os.getenv("FITBIT_CLIENT_ID", "")
    )
    google_health_client_secret: str = field(
        default_factory=lambda: os.getenv("GOOGLE_HEALTH_CLIENT_SECRET") or os.getenv("FITBIT_CLIENT_SECRET", "")
    )
    google_health_auth_url: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_HEALTH_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth"
        )
    )
    google_health_token_url: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_HEALTH_TOKEN_URL", "https://oauth2.googleapis.com/token"
        )
    )
    google_health_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_HEALTH_API_BASE_URL", "https://fitness.googleapis.com/fitness/v1"
        )
    )

    # Oura Ring OAuth 2.0 PKCE & API settings
    oura_client_id: str = field(default_factory=lambda: os.getenv("OURA_CLIENT_ID", ""))
    oura_client_secret: str = field(
        default_factory=lambda: os.getenv("OURA_CLIENT_SECRET", "")
    )
    oura_auth_url: str = field(
        default_factory=lambda: os.getenv(
            "OURA_AUTH_URL", "https://cloud.ouraring.com/oauth/authorize"
        )
    )
    oura_token_url: str = field(
        default_factory=lambda: os.getenv(
            "OURA_TOKEN_URL", "https://api.ouraring.com/oauth/token"
        )
    )
    oura_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "OURA_API_BASE_URL", "https://api.ouraring.com/v2"
        )
    )

    # Whoop Developer OAuth 2.0 PKCE & API settings
    whoop_client_id: str = field(default_factory=lambda: os.getenv("WHOOP_CLIENT_ID", ""))
    whoop_client_secret: str = field(
        default_factory=lambda: os.getenv("WHOOP_CLIENT_SECRET", "")
    )
    whoop_auth_url: str = field(
        default_factory=lambda: os.getenv(
            "WHOOP_AUTH_URL", "https://api.prod.whoop.com/oauth/oauth2/auth"
        )
    )
    whoop_token_url: str = field(
        default_factory=lambda: os.getenv(
            "WHOOP_TOKEN_URL", "https://api.prod.whoop.com/oauth/oauth2/token"
        )
    )
    whoop_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "WHOOP_API_BASE_URL", "https://api.prod.whoop.com/developer/v2"
        )
    )

    # Withings Health OAuth 2.0 PKCE & API settings
    withings_client_id: str = field(default_factory=lambda: os.getenv("WITHINGS_CLIENT_ID", ""))
    withings_client_secret: str = field(
        default_factory=lambda: os.getenv("WITHINGS_CLIENT_SECRET", "")
    )
    withings_auth_url: str = field(
        default_factory=lambda: os.getenv(
            "WITHINGS_AUTH_URL", "https://account.withings.com/oauth2_user/authorize2"
        )
    )
    withings_token_url: str = field(
        default_factory=lambda: os.getenv(
            "WITHINGS_TOKEN_URL", "https://wbsapi.withings.net/v2/oauth2"
        )
    )
    withings_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "WITHINGS_API_BASE_URL", "https://wbsapi.withings.net"
        )
    )

    @property
    def oauth_redirect_uri(self) -> str:
        override = os.getenv("OAUTH_REDIRECT_URI") or os.getenv("GARMIN_REDIRECT_URI")
        if override:
            return override.strip()
        return f"{self.public_base_url.rstrip('/')}/cloud/callback"

    @property
    def resolved_outbox_dir(self) -> str:
        if self.outbox_dir:
            return self.outbox_dir
        parent = os.path.dirname(self.storage_path) or "/data"
        return os.path.join(parent, "outbox")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
