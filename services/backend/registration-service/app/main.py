from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.charite_client import mock_lookup_user_in_charite
from app.crud import create_registration
from app.db import SessionLocal, Base, engine
from app.jwt_auth import JWTAuthService
from app.mail import EmailService
from app.models import PatientResponse, PatientRequest, RegistrationToken, RegisterResponse
from app.token import RegistrationTokenService

app = FastAPI(title="Test", version="0.1.0", description="Test")
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "OK"}


@app.post("/register/patient", response_model=RegisterResponse)
async def register_patient(payload: PatientRequest, db: Session = Depends(get_db)):
    charite_info = await mock_lookup_user_in_charite(payload.patient_id)

    if not charite_info:
        raise HTTPException(status_code=404, detail="User not found")

    start_time = datetime.fromisoformat(payload.event_start_date.replace('Z', '+00:00'))

    reg = await create_registration(
        db=db,
        username=payload.patient_id,
        context_name=payload.context_id,
        watch_id=payload.watch_id,
        phone_id=payload.phone_id,
        start_time=start_time,
        duration=payload.event_duration,
    )

    db.commit()

    # Generate new Token
    token_obj = RegistrationTokenService.create_registration_token(
        db,
        reg.id,
        start_time=payload.event_start_date.replace('Z', '+00:00'),
        duration=payload.event_duration,
    )

    token_id = token_obj.id

    # send the token via E-Mail to the user-mail
    test_mail = payload.patient_mail
    appointment_date = datetime.fromisoformat(payload.appointment_date.replace('Z', '+00:00'))

    b = await EmailService.send_registration_mail(test_mail, token_id, appointment_date)

    if not b:
        raise HTTPException(status_code=404, detail="Email not found")

    return RegisterResponse(
        status="OK",
        message=f"Registered successfully",
    )


@app.get("/onboard/{token_id}", response_model=PatientResponse)
async def onboard_patient(token_id: str, db: Session = Depends(get_db)):
    print("Now checking if it's token is valid")
    valid, message = RegistrationTokenService.validate_and_consume_token(db, token_id)

    if not valid:
        raise HTTPException(status_code=404, detail=message)

    token = RegistrationTokenService.get_token(db, token_id)

    event_id = token.event_id

    jwt_auth = JWTAuthService.generate_auth_token(
        event_id=event_id,
        event_start_time=token.start_time,
        event_duration=token.duration,
    )


    return PatientResponse(
        status="OK",
        message=message,
        reg_id=jwt_auth,
    )


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
