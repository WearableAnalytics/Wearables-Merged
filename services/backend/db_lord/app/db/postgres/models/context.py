from sqlalchemy import Column, String, Table, Uuid, func

from .metadata import metadata

contexts = Table(
    "contexts",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("group_name", String, nullable=False),
    Column("coordinator", String),
)
