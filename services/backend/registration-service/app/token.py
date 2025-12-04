import secrets
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import RegistrationToken


class RegistrationTokenService:
    TOKEN_LENGTH = 16

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(RegistrationTokenService.TOKEN_LENGTH)

    @staticmethod
    def create_registration_token(
            db: Session,
            event_id: str,
            max_retries: int = 3,
    ) -> Optional[RegistrationToken]:
        for attempt in range(max_retries):
            try:
                token_id = RegistrationTokenService.generate_token()

                reg_token = RegistrationToken(
                    id=token_id,
                    event_id=event_id,
                    status="PENDING"
                )

                db.add(reg_token)
                db.commit()
                db.refresh(reg_token)

                return reg_token

            except IntegrityError:
                db.rollback()

                if attempt == max_retries - 1:
                    raise ValueError("Failed to generate unique Token expired")

            except Exception as e:
                db.rollback()
                raise e
        return None

    @staticmethod
    def get_token(db: Session, token_id: str) -> Optional[RegistrationToken]:
        reg_token = db.query(RegistrationToken).filter(RegistrationToken.id == token_id).first()
        return reg_token


    @staticmethod
    def validate_and_consume_token(
            db: Session,
            token_id: str,
    ) -> tuple[bool, str] | None:

        token = RegistrationToken.get_token(db, token_id)

        if not token:
            return False, "Token not found"

        if str(token.status).capitalize() != "PENDING":
            return False, "Token already used"

        try:
            token.status = "DONE"
            db.commit()
            return True, "Token validated successfully"
        except Exception as e:
            db.rollback()
            return False, f"Failed to validate token: {e}"