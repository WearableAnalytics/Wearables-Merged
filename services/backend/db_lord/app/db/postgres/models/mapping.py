from sqlalchemy import JSON, Column, ForeignKey, String, Table, Uuid, func

from .metadata import metadata

mappings = Table(
    "mappings",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("version", String, nullable=False),
    Column("full_mapping", JSON, nullable=False),
)
map_trees = Table(
    "map_trees",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("version", String, nullable=False),
    Column("map_tree", JSON, nullable=False),
    Column("category", String, nullable=False),
    Column("mapping_id", Uuid, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False),
)
