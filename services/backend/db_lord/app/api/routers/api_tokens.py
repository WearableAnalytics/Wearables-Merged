from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import ApiTokenServiceDep
from app.schemas.api_token import ApiTokenCreate, ApiTokenResponse, ApiTokenRevoke, ApiTokenVerify

router = APIRouter()


@router.post("/", response_model=ApiTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_api_token(item_in: ApiTokenCreate, service: ApiTokenServiceDep):
    return await service.create(item_in)


@router.get("/", response_model=list[ApiTokenResponse])
async def list_api_tokens(
    service: ApiTokenServiceDep,
    owner_email: str | None = Query(None, description="Only tokens of this owner."),
    include_revoked: bool = Query(False),
):
    return await service.list(owner_email, include_revoked)


@router.post("/verify", response_model=ApiTokenResponse, summary="Look up an active token by its hash")
async def verify_api_token(item_in: ApiTokenVerify, service: ApiTokenServiceDep):
    return await service.verify(item_in.token_hash)


@router.post("/{id:uuid}/revoke", response_model=ApiTokenResponse)
async def revoke_api_token(id: UUID, item_in: ApiTokenRevoke, service: ApiTokenServiceDep):
    return await service.revoke(id, item_in.revoked_by)
