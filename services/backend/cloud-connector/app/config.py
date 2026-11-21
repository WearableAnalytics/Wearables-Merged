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

    @property
    def oauth_redirect_uri(self) -> str:
        override = os.getenv("OAUTH_REDIRECT_URI") or os.getenv("GARMIN_REDIRECT_URI")
        if override:
            return override.strip()
        return f"{self.public_base_url.rstrip('/')}/cloud/callback"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
