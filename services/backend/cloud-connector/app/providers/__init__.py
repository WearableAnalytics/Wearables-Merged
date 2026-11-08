from typing import Dict, List, Type
from .base import BaseCloudProvider
from .garmin import GarminProvider

_PROVIDERS: Dict[str, Type[BaseCloudProvider]] = {
    "garmin": GarminProvider,
}


def get_provider(name: str) -> BaseCloudProvider:
    provider_cls = _PROVIDERS.get(name.lower())
    if not provider_cls:
        raise ValueError(f"Unknown cloud provider '{name}'. Available: {list(_PROVIDERS.keys())}")
    return provider_cls()


def list_available_providers() -> List[str]:
    return list(_PROVIDERS.keys())
