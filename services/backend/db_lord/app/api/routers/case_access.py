"""Case authority and identifying metadata for the BFF workload."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.control_auth import require_control_write
from app.api.dependencies import PgSessionDep
from app.schemas.case_access import AccessDecision, AccessDecisionResponse, AccessPage, AccessPut, AccessResponse, Actor
from app.schemas.clinical_metadata import ClinicalCaseMetadata, ClinicalMetadataPage
from app.services.case_access_service import CaseAccessService
from app.services.clinical_metadata import ClinicalMetadata

router = APIRouter(dependencies=[Depends(require_control_write)])


def query_actor(actor_id: UUID, actor_auth_version: int = Query(ge=1)) -> Actor:
    return Actor(actor_id=actor_id, actor_auth_version=actor_auth_version)


QueryActor = Annotated[Actor, Depends(query_actor)]


@router.put("/case-access/{case_id:uuid}/{user_id:uuid}", response_model=AccessResponse)
async def put_access(case_id: UUID, user_id: UUID, item: AccessPut, db: PgSessionDep):
    return await CaseAccessService(db).put_access(case_id, user_id, item)


@router.get("/case-access/{case_id:uuid}/{user_id:uuid}", response_model=AccessResponse)
async def get_access(case_id: UUID, user_id: UUID, actor: QueryActor, db: PgSessionDep):
    return await CaseAccessService(db).get_access(case_id, user_id, actor)


@router.post("/decisions/case-access", response_model=AccessDecisionResponse)
async def decide_access(item: AccessDecision, db: PgSessionDep):
    return await CaseAccessService(db).decide_access(item)


@router.get("/case-access", response_model=AccessPage)
async def page_access(
    actor: QueryActor, db: PgSessionDep, limit: int = Query(100, ge=1, le=100), after: UUID | None = None
):
    return await CaseAccessService(db).list_access(actor, limit, after)


@router.get("/clinical-cases", response_model=ClinicalMetadataPage)
async def page_metadata(
    actor: QueryActor,
    db: PgSessionDep,
    limit: int = Query(100, ge=1, le=100),
    after: UUID | None = None,
    patient_id: UUID | None = None,
):
    return await ClinicalMetadata(db).page(actor, limit, after, patient_id=patient_id)


@router.get("/clinical-cases/{case_id:uuid}", response_model=ClinicalCaseMetadata)
async def one_metadata(case_id: UUID, actor: QueryActor, db: PgSessionDep):
    return await ClinicalMetadata(db).one(case_id, actor)
