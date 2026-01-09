from sqlalchemy import Column, DateTime, ForeignKey, Table, Uuid

from .metadata import metadata

# 1. Cases <> Contexts
case_contexts = Table(
    "case_contexts",
    metadata,
    Column("case_id", Uuid, ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
    Column("context_id", Uuid, ForeignKey("contexts.id", ondelete="CASCADE"), primary_key=True),
)

# 2. Cases <> Devices
case_devices = Table(
    "case_devices",
    metadata,
    Column("case_id", Uuid, ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
    # The composite PK index only speeds up queries with case_id etc. but we also want to have fast lookups by device_id
    Column("device_id", Uuid, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("assigned_from", DateTime(timezone=True), nullable=False, primary_key=True),
    Column("assigned_to", DateTime(timezone=True), nullable=True),
)

# 3. Cases <> Wearables
case_wearables = Table(
    "case_wearables",
    metadata,
    Column("case_id", Uuid, ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
    Column("wearable_id", Uuid, ForeignKey("wearables.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("assigned_from", DateTime(timezone=True), nullable=False, primary_key=True),
    Column("assigned_to", DateTime(timezone=True), nullable=True),
)
