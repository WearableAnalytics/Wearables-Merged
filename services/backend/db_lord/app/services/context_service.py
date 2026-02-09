from app.db.postgres.orm import Context
from app.db.postgres.repos.context_repo import ContextRepo
from app.schemas.context import ContextCreate, ContextUpdate
from app.services.base import BaseService


class ContextService(BaseService[Context, ContextCreate, ContextUpdate, ContextRepo]):
    def __init__(self, repo: ContextRepo):
        super().__init__(repo)
