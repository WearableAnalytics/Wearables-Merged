import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Settings:
    postgres_user: str = os.getenv('POSTGRES_USER', "test")
    postgres_password: str = os.getenv('POSTGRES_PASSWORD', "password")
    postgres_db: str = os.getenv('POSTGRES_DB', "db")
    database_url: str = os.getenv('DATABASE_URL', "postgresql://test:password@postgres/test")
    charite_url: str = os.getenv('CHARITE_URL', "http://localhost:9090")
    secret_key: str = os.getenv('SECRET_KEY', "secret")
    token_expiration: int = os.getenv('TOKEN_EXPIRATION', 60 * 15)


@lru_cache()
def get_settings() -> Settings:
    return Settings()