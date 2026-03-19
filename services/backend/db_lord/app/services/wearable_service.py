from uuid import UUID

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import Wearable
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.schemas.assignment import WearableAssignmentResponse
from app.schemas.wearable import WearableCreate, WearableUpdate
from app.services.base import BaseService


class WearableService(BaseService[Wearable, WearableCreate, WearableUpdate, WearableRepo]):
    def __init__(self, repo: WearableRepo):
        super().__init__(repo)

    async def get_assignments(self, id: UUID) -> list[WearableAssignmentResponse]:
        wearable = await self.repo.get_with_assignments(id)
        if not wearable:
            raise EntityNotFoundError("Wearable", id)
        return [WearableAssignmentResponse.model_validate(item) for item in wearable.case_assignments]
