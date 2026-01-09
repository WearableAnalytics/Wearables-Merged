from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.context import contexts
from app.db.postgres.repos.base import BaseRepo
from app.schemas.context import ContextCreate, ContextUpdate


class ContextRepo(BaseRepo[contexts, ContextCreate, ContextUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(contexts, db)
