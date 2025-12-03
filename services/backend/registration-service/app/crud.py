import uuid

from passlib.context import CryptContext
from sqlalchemy.orm import Session
import app.models as models

async def create_registration(db: Session, username: str, context_name: str, watch_id: str, phone_id: str):
    reg_id = str(uuid.uuid4())

    reg = models.PatientMaster(
        id=reg_id,
        patient_id=username,
        phone_id=phone_id,
        watch_id=watch_id,
        context_id=context_name,
    )

    db.add(reg)
    db.flush()
    return reg