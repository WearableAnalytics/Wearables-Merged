from typing import Dict, List, Type
from .base import BaseCloudProvider
from .garmin import GarminProvider
from .polar import PolarProvider
from .google_health import GoogleHealthProvider
from .oura import OuraProvider
from .whoop import WhoopProvider

_PROVIDERS: Dict[str, Type[BaseCloudProvider]] = {
    "garmin": GarminProvider,
    "polar": PolarProvider,
    "google_health": GoogleHealthProvider,
    "fitbit": GoogleHealthProvider,  # for Fitbit & Pixel Watch
    "oura": OuraProvider,
    "whoop": WhoopProvider,
}


def get_provider(name: str) -> BaseCloudProvider:
    provider_cls = _PROVIDERS.get(name.lower())
    if not provider_cls:
        raise ValueError(f"Unknown cloud provider '{name}'. Available: {list(_PROVIDERS.keys())}")
    return provider_cls()


def list_available_providers() -> List[str]:
    return list(_PROVIDERS.keys())
