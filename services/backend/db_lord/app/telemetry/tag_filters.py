from app.core.utils import ordered_unique
from app.telemetry.types import TelemetryTagInput, TelemetryTags


def merge_tag_filter(tags: TelemetryTags, key: str, incoming: TelemetryTagInput) -> None:
    existing = tags.get(key)
    incoming_values = incoming if isinstance(incoming, list) else [incoming]

    if existing is None:
        tags[key] = ordered_unique(incoming_values)
        return

    tags[key] = ordered_unique([*existing, *incoming_values])
