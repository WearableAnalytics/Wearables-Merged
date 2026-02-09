from app.db.postgres.orm import Patient
from app.db.postgres.repos.patient_repo import PatientRepo
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services.base import BaseService


class PatientService(BaseService[Patient, PatientCreate, PatientUpdate, PatientRepo]):
    def __init__(self, repo: PatientRepo):
        super().__init__(repo)
