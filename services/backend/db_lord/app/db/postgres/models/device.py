from sqlalchemy import Column, String, Table, Uuid, func

from .metadata import metadata

devices = Table(
    "devices",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("serial_nr", String, nullable=False, unique=True),
    Column("model", String, nullable=False),
    Column("manufacturer", String),
    Column("os_version", String, nullable=False),
)
