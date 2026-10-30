import os
from functools import lru_cache
from dataclasses import dataclass, field


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

    # Central public base URL for all OAuth callbacks
    public_base_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://localhost")
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

    @property
    def oauth_redirect_uri(self) -> str:
        override = os.getenv("OAUTH_REDIRECT_URI") or os.getenv("GARMIN_REDIRECT_URI")
        if override:
            return override.strip()
        return f"{self.public_base_url.rstrip('/')}/cloud/callback"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
