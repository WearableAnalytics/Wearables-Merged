from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine

async_engine = create_async_engine(get_settings().database_url, echo=True, pool_pre_ping=True)
