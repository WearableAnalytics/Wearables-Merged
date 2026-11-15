"""Apply the ingestion schema using a migration role, before starting runtime workers."""

import asyncio
import os
from pathlib import Path

from psycopg import AsyncConnection


async def main():
    async with await AsyncConnection.connect(os.environ["INGEST_DATABASE_URL"], autocommit=True) as connection:
        await connection.execute((Path(__file__).parents[1] / "migrations/001_ingestion.sql").read_text())


if __name__ == "__main__":
    asyncio.run(main())
