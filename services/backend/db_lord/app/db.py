from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

async_engine = create_async_engine(get_settings().database_url, echo=True)