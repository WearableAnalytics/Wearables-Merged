from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
from ..models import IngestPayload


class BaseCloudProvider(ABC):
    """Abstract base class for all cloud wearable providers (Garmin, Fitbit, etc.).
    Open for extension with new providers,closed for modification of existing ingestion pipelines
    """

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
