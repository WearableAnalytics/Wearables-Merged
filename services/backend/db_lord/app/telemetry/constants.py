"""
Kind of a leftover from when we differentiated between the different types of tags (core vs non core).
Should probably be moved somewhere else.
"""

TELEMETRY_TAG_NAMES: tuple[str, ...] = (
    "patient_id",
    "device_id",
    "wearable_id",
    "case_id",
    "context_id",
    "mapping_id",
    "dot_dependency_file_id",
)

TELEMETRY_NON_TAG_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "measurement",
        "bucket",
        "start",
        "end",
        "field",
        "fields",
        "limit",
        "tag",
    }
)

RESERVED_TELEMETRY_QUERY_KEYS: frozenset[str] = TELEMETRY_NON_TAG_QUERY_KEYS | frozenset(TELEMETRY_TAG_NAMES)

TELEMETRY_DEFAULT_LIMIT = 100
TELEMETRY_MAX_LIMIT = 10_000
