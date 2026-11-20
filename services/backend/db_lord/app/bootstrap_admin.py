"""Initialize only configured administrators; never restore an existing account's authority."""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.schemas.control import UserCreate
from app.services.control_service import ControlService


async def initialize(email: str):
    engine = create_async_engine(settings.POSTGRES_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            user = await ControlService(db).create_user(UserCreate(email=email), bootstrap=True)
            print(f"Administrator initialization checked; current status: {user.status}.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(initialize(args.email))
