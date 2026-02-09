from app.db.postgres.orm import Wearable
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.schemas.wearable import WearableCreate, WearableUpdate
from app.services.base import BaseService


class WearableService(BaseService[Wearable, WearableCreate, WearableUpdate, WearableRepo]):
    def __init__(self, repo: WearableRepo):
        super().__init__(repo)
