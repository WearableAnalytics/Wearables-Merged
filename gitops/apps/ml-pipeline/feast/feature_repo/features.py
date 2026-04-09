"""
Feature view definitions for wearables data.

These define how raw Silver-layer data maps to ML features.
The prediction job and training pipelines both reference these definitions
to guarantee feature consistency (training-serving skew prevention).
"""
from datetime import timedelta

from feast import (
    FeatureView,
    Field,
    PushSource,
    FileSource,
)
from feast.types import Float64, String, UnixTimestamp
from entities import device

# ---------------------------------------------------------------------------
# Push source: the streaming pipeline pushes features here in real-time
# ---------------------------------------------------------------------------
wearables_push_source = PushSource(
    name="wearables_push",
    batch_source=FileSource(
        name="wearables_offline",
        path="",  # Not used directly - push source is the primary path
        timestamp_field="event_time",
    ),
)

# ---------------------------------------------------------------------------
# Heart-rate feature view — pushed from the streaming Silver layer
# ---------------------------------------------------------------------------
heart_rate_features = FeatureView(
    name="heart_rate_features",
    entities=[device],
    schema=[
        Field(name="heart_rate_value", dtype=Float64, description="Raw heart-rate sensor reading"),
        Field(name="device_category", dtype=String, description="Device category tag"),
        Field(name="device_version", dtype=String, description="Device firmware version tag"),
        Field(name="event_time", dtype=UnixTimestamp, description="Sensor event timestamp"),
    ],
    source=wearables_push_source,
    ttl=timedelta(hours=24),
    online=True,
    tags={"team": "ml", "source": "silver-layer"},
)
