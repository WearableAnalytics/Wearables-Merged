from sqlalchemy import Column, Date, Numeric, String, Table, Uuid, func

from .metadata import metadata

patients = Table(
    "patients",
    metadata,
    # Generates uuid7 by the database by default should be faster then in python. Also stops people from generating invalid uuids
    # Also ensures fixes clock drift issues with uuid generation on the app side vs db side
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("charite_id", Uuid, nullable=False),
    Column("name", String, nullable=False),
    Column("sex", String),
    Column("dob", Date),
    Column("weight", Numeric(6, 2)),
    Column("height", Numeric(4, 2)),
)
