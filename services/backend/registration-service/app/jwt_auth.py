import jwt
from datetime import datetime

from app.config import get_settings


class JWTAuthService:

    @staticmethod
    def generate_auth_token(event_id: str, event_start_time: str, event_duration: str) -> str:

        start_time = datetime.fromisoformat(event_start_time.replace('Z', '+00:00'))
        start_timestamp = int(start_time.timestamp())

        duration_seconds = int(event_duration)


        payload = {
            "sub": event_id,
            "iat": start_timestamp,
            "exp": start_timestamp + duration_seconds,
        }

        token = jwt.encode(payload, get_settings().jwt_secret, get_settings().jwt_algorithm)
        return token