"""Read InfluxDB line-protocol tags from the raw Kafka payload with Spark column expressions.

Only built-in regex functions are used (no Python UDF), so the parsing runs in the JVM on
executors and needs nothing shipped besides this file on the driver.

Line protocol escapes ` `, `,` and `=` in tag values with a backslash, so the patterns
skip escaped characters instead of splitting on them.
"""
from pyspark.sql import Column
from pyspark.sql.functions import coalesce, lit, regexp_extract, regexp_replace, when

# Measurement and tags: everything before the first unescaped space.
_HEAD = r"^((?:[^ \\]|\\.)*)"
PATIENT_REFERENCE_PREFIX = "Patient/"


def _tag(head: Column, key: str) -> Column:
    """Unescaped value of tag `key` in the LP head, or null when absent or empty."""
    raw = regexp_extract(head, rf"(?:^|,){key}=((?:[^,\\]|\\.)*)", 1)
    value = regexp_replace(raw, r"\\(.)", "$1")
    return when(value != "", value)


def lp_head(payload: Column) -> Column:
    return regexp_extract(payload, _HEAD, 1)


def patient_id(payload: Column) -> Column:
    """Patient of an LP record.

    The mapper writes `patient-id`. Records produced before that tag existed only carry
    `device-id-reference=Patient/<id>`, so those fall back to it; anything else is null.
    """
    head = lp_head(payload)
    reference = _tag(head, "device-id-reference")
    legacy = when(
        reference.startswith(PATIENT_REFERENCE_PREFIX),
        regexp_replace(reference, "^" + PATIENT_REFERENCE_PREFIX, ""),
    )
    return coalesce(_tag(head, "patient-id"), legacy, lit(None).cast("string"))
