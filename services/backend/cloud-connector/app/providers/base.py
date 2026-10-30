from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from ..models import IngestPayload


class BaseCloudProvider(ABC):
    """Abstract base class for all cloud wearable providers (Garmin, Fitbit, etc.)"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier of the provider (e.g. 'garmin', 'fitbit')"""
        pass

    @abstractmethod
    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        """Validates whether the provided tokens or credentials are valid"""
        pass

    @abstractmethod
    async def fetch_telemetry(
        self,
        patient_id: str,
        credentials: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> IngestPayload:
        """Fetches telemetry data from the provider cloud and normalizes it into IngestPayload"""
        pass

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generates a (code_verifier, code_challenge) pair for OAuth 2.0 PKCE"""
        raise NotImplementedError(f"OAuth 2.0 PKCE is not implemented for {self.provider_name}")

    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None,
    ) -> str:
        """Builds the OAuth 2.0 user authorization URL"""
        raise NotImplementedError(f"OAuth 2.0 authorization is not implemented for {self.provider_name}")

    async def exchange_code_for_token(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchanges an OAuth 2.0 authorization code for access and refresh tokens"""
        raise NotImplementedError(f"OAuth 2.0 token exchange is not implemented for {self.provider_name}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refreshes an expired OAuth 2.0 access token using a refresh token"""
        raise NotImplementedError(f"OAuth 2.0 token refresh is not implemented for {self.provider_name}")

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetches the provider's unique userId and granted permissions for the authorized user"""
        raise NotImplementedError(f"User info lookup is not implemented for {self.provider_name}")

    async def deregister_user(self, access_token: str) -> bool:
        """Deregisters/disconnects a user's registration at the provider"""
        return True

    def parse_webhook_payload(
        self,
        data: Dict[str, Any],
        resolve_patient_id: Callable[[str], Optional[str]],
        default_patient_id: Optional[str] = None,
    ) -> List[IngestPayload]:
        """Parses an incoming webhook push payload into one or more normalized IngestPayloads"""
        return []
