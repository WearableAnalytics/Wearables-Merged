import os
from functools import lru_cache
from dataclasses import dataclass


@dataclass
class Settings:
    app_name: str = "Wearables Cloud Connector"
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "wearables-raw")
    kafka_client_id: str = os.getenv("KAFKA_CLIENT_ID", "wearables-cloud-connector")
    kafka_connect_retries: int = int(os.getenv("KAFKA_CONNECT_RETRIES", "5"))
    kafka_connect_backoff: float = float(os.getenv("KAFKA_CONNECT_BACKOFF", "1.0"))
    garmin_api_base_url: str = os.getenv("GARMIN_API_BASE_URL", "https://health-api.garmin.com/wellness-api/rest")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
