CORE_TELEMETRY_TAG_ORDER: tuple[str, ...] = (
    "patient_id",
    "device_id",
    "wearable_id",
    "case_id",
    "context_id",
    "mapping_id",
    "dot_dependency_file_id",
)
CORE_TELEMETRY_TAG_KEYS: frozenset[str] = frozenset(CORE_TELEMETRY_TAG_ORDER)

TELEMETRY_NON_TAG_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "measurement",
        "bucket",
        "start",
        "end",
        "field",
        "fields",
        "size",
        "cursor",
        "tag",
    }
)

RESERVED_TELEMETRY_QUERY_KEYS: frozenset[str] = TELEMETRY_NON_TAG_QUERY_KEYS | CORE_TELEMETRY_TAG_KEYS

TELEMETRY_DEFAULT_PAGE_SIZE = 100
TELEMETRY_MAX_PAGE_SIZE = 10_000
