from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import Context
from app.db.postgres.repos.base import BaseRepo
from app.schemas.context import ContextCreate, ContextUpdate


class ContextRepo(BaseRepo[Context, ContextCreate, ContextUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Context, db)
