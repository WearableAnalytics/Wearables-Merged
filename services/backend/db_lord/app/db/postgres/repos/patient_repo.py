from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.patient import patients
from app.db.postgres.repos.base import BaseRepo
from app.schemas.patient import PatientCreate, PatientUpdate


class PatientRepo(BaseRepo[patients, PatientCreate, PatientUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(patients, db)
