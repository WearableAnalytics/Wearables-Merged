"""
Entity definitions for the wearables feature store.
"""
from feast import Entity, ValueType

# Primary entity: a wearable device
device = Entity(
    name="device_id",
    value_type=ValueType.STRING,
    description="Unique wearable device identifier",
)
