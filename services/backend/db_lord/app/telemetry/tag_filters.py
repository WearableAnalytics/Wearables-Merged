from __future__ import annotations

from app.telemetry.types import TelemetryTagInput, TelemetryTags


def merge_tag_filter(
    tags: TelemetryTags,
    key: str,
    incoming: TelemetryTagInput,
) -> None:
    existing = tags.get(key)
    incoming_values = incoming if isinstance(incoming, list) else [incoming]

    if existing is None:
        tags[key] = list(dict.fromkeys(incoming_values))
        return

    tags[key] = list(dict.fromkeys([*existing, *incoming_values]))
