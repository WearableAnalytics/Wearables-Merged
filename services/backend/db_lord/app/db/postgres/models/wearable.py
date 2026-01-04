from sqlalchemy import Column, Enum, String, Table, Uuid, func

from app.schemas.common import HardwareStatus

from .metadata import metadata

wearables = Table(
    "wearables",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("serial_nr", String, nullable=False, unique=True),
    Column("model", String, nullable=False),
    Column("manufacturer", String),
    Column("os_version", String, nullable=False),
    Column(
        "status",
        Enum(HardwareStatus, name="hardware_status", native_enum=True),
        nullable=False,
        server_default=HardwareStatus.AVAILABLE.value,
    ),
)
