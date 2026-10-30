from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.control_auth import require_control_read, require_control_write
from app.api.dependencies import PgSessionDep
from app.schemas.control import (
    LoginChallengeConsume,
    LoginChallengeCreate,
    RevokeSessions,
    UserCreate,
    UserDecision,
    UserDecisionResponse,
    UserPage,
    UserPatch,
    UserResponse,
    UserStatus,
)
from app.services.control_service import ControlService
from app.services.login_challenge import LoginChallengeService

router = APIRouter()
read = [Depends(require_control_read)]
write = [Depends(require_control_write)]


def service(db: PgSessionDep) -> ControlService:
    return ControlService(db)


Service = Annotated[ControlService, Depends(service)]


@router.get("/users", response_model=UserPage, dependencies=write)
async def list_users(
    control: Service,
    email: str | None = Query(None, max_length=320),
    status: UserStatus | None = None,
    limit: int = Query(100, ge=1, le=100),
    after: UUID | None = None,
):
    return await control.users(email, status, limit, after)


@router.post("/users", response_model=UserResponse, status_code=201, dependencies=write)
async def create_user(item: UserCreate, control: Service):
    return await control.create_user(item)


@router.post("/users/bootstrap", response_model=UserResponse, dependencies=write)
async def bootstrap_user(item: UserCreate, control: Service):
    return await control.create_user(item, bootstrap=True)


@router.get("/users/{user_id:uuid}", response_model=UserResponse, dependencies=write)
async def get_user(user_id: UUID, control: Service):
    return await control.user(user_id)


@router.patch("/users/{user_id:uuid}", response_model=UserResponse, dependencies=write)
async def patch_user(user_id: UUID, item: UserPatch, control: Service):
    return await control.patch_user(user_id, item)


@router.post("/users/{user_id:uuid}/revoke-sessions", response_model=UserResponse, dependencies=write)
async def revoke_sessions(user_id: UUID, item: RevokeSessions, control: Service):
    return await control.revoke_sessions(user_id, item)


@router.post("/decisions/user", response_model=UserDecisionResponse, dependencies=read)
async def decide_user(item: UserDecision, control: Service):
    return await control.decide_user(item)


@router.post("/login-challenges", dependencies=write)
async def issue_login_challenge(item: LoginChallengeCreate, db: PgSessionDep):
    await LoginChallengeService(db).issue(item)
    return {"issued": True}


@router.post("/login-challenges/consume", response_model=UserResponse, dependencies=write)
async def consume_login_challenge(item: LoginChallengeConsume, db: PgSessionDep):
    return await LoginChallengeService(db).consume(item.token_hash)
