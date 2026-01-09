import uvicorn
from app.db_handler import AsyncDbHandler, ResourceConflictError, get_async_db_handler
from fastapi import Depends, FastAPI, HTTPException, Query
from models.sql_schema import (
    Case,
    CaseCreate,
    CaseLinkContextRequest,
    CaseLinkDeviceRequest,
    CaseLinkWearableRequest,
    Context,
    ContextBase,
    Device,
    DeviceBase,
    Patient,
    PatientBase,
    Wearable,
)
from sqlalchemy.exc import IntegrityError
from starlette import status
from starlette.responses import JSONResponse

from app.db import async_engine

# TODO: add pagination to list endpoints
# TODO: add logging
# TODO: probably dont actually just requery the whole object after creation or updates etc.
app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "OK"}


# Patients endpoints
@app.post(
    "/patients",
    response_model=Patient,
    status_code=status.HTTP_201_CREATED,
)
async def post_patients(payload: PatientBase, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            patient = await handler.create_patient(conn=conn, patient_data=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Patient already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return patient


@app.get(
    "/patients/{patient_id}",
    response_model=Patient,
    status_code=status.HTTP_200_OK,
)
async def get_patient_endpoint(patient_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.connect() as conn:
        patient = await handler.get_patient(conn=conn, patient_id=patient_id)

        if patient is None:
            raise HTTPException(status_code=404, detail="Patient not found")

        return patient


@app.put(
    "/patients/{patient_id}",
    response_model=Patient,
    status_code=status.HTTP_200_OK,
)
async def put_patient_endpoint(
    patient_id: str, payload: PatientBase, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        patient = await handler.update_patient(conn=conn, patient_id=patient_id, patient_data=payload)

        if patient is not None:
            return patient

        try:
            patient = await handler.create_patient(conn=conn, patient_data=payload, id=patient_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Patient already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        # i think technically model_dump_json is a bit faster but this should be fine
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=patient.model_dump(mode="json"))


@app.put("/patients/{patient_id}", response_model=Patient)
async def put_patient_endpoint(
    patient_id: str, payload: PatientBase, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        return await handler.upsert_patient(conn=conn, patient_id=patient_id, patient_data=payload)


@app.delete(
    "/patients/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_patient_endpoint(patient_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_patient(conn=conn, patient_id=patient_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Patient cannot be deleted due to conflicts")

        if not deleted:
            raise HTTPException(status_code=404, detail="Patient not found")


# Wearables endpoints
@app.get(
    "/wearables/{wearable_id}",
    response_model=Wearable,
    status_code=status.HTTP_200_OK,
)
async def get_wearable_endpoint(wearable_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.connect() as conn:
        wearable = await handler.get_wearable(conn=conn, wearable_id=wearable_id)

        if wearable is None:
            raise HTTPException(status_code=404, detail="Wearable not found")

        return wearable


@app.post(
    "/wearables/{wearable_id}",
    response_model=Wearable,
    status_code=status.HTTP_201_CREATED,
)
async def post_wearable_endpoint(
    payload: DeviceBase, wearable_id: str | None = None, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        try:
            wearable = await handler.create_wearable(conn=conn, wearable_base=payload, id=wearable_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Wearable already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return wearable


@app.put(
    "/wearables/{wearable_id}",
    response_model=Wearable,
    status_code=status.HTTP_200_OK,
)
async def put_wearable_endpoint(
    wearable_id: str, payload: DeviceBase, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        wearable = await handler.update_wearable(conn=conn, wearable_id=wearable_id, wearable_base=payload)

        if wearable is not None:
            return wearable

        try:
            wearable = await handler.create_wearable(conn=conn, wearable_base=payload, id=wearable_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Wearable already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=wearable.model_dump(mode="json"))


@app.delete(
    "/wearables/{wearable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_wearable_endpoint(wearable_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_wearable(conn=conn, wearable_id=wearable_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Wearable not found")

        if not deleted:
            raise HTTPException(status_code=404, detail="Wearable not found")


# Devices endpoints
@app.get(
    "/devices/{device_id}",
    response_model=Device,
    status_code=status.HTTP_200_OK,
)
async def get_devices_endpoint(device_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.connect() as conn:
        device = await handler.get_device(conn=conn, device_id=device_id)

        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

        return device


@app.post("/devices", response_model=Device, status_code=status.HTTP_201_CREATED)
async def post_devices_endpoint(payload: DeviceBase, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            device = await handler.create_device(conn=conn, device_base=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Device already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return device


@app.put(
    "/devices/{device_id}",
    response_model=Device,
    status_code=status.HTTP_200_OK,
)
async def put_devices_endpoint(
    device_id: str, payload: DeviceBase, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        device = await handler.update_device(conn=conn, device_id=device_id, device_base=payload)

        if device is not None:
            return device

        try:
            device = await handler.create_device(conn=conn, device_base=payload, id=device_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Device already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=device.model_dump(mode="json"))


@app.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_devices_endpoint(device_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_device(conn=conn, device_id=device_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Device cannot be deleted due to conflict")

        if not deleted:
            raise HTTPException(status_code=404, detail="Device not found")


# Contexts endpoints
@app.get(
    "/contexts/{context_id}",
    response_model=Context,
    status_code=status.HTTP_200_OK,
)
async def get_context_endpoint(context_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.connect() as conn:
        context = await handler.get_context(conn=conn, context_id=context_id)

    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")

    return context


@app.post(
    "/contexts",
    response_model=Context,
    status_code=status.HTTP_201_CREATED,
)
async def post_context_endpoint(payload: ContextBase, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            context = await handler.create_context(conn=conn, context_base=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Context already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return context


@app.put(
    "/contexts/{context_id}",
    response_model=Context,
    status_code=status.HTTP_200_OK,
)
async def put_context_endpoint(
    context_id: str, payload: ContextBase, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        context = await handler.update_context(conn=conn, context_id=context_id, context_base=payload)

        if context is not None:
            return context

        try:
            context = await handler.create_context(conn=conn, context_base=payload, id=context_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Cannot update context due to conflict")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=context.model_dump(mode="json"))


@app.delete(
    "/contexts/{context_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_context_endpoint(context_id: str, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_context(conn=conn, context_id=context_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Cannot delete context due to conflict")

        if not deleted:
            raise HTTPException(status_code=404, detail="Context not found")


# Case endpoints
@app.post("/cases", response_model=Case, status_code=status.HTTP_201_CREATED)
async def create_case(payload: CaseCreate, handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            return await handler.create_case(conn, payload)
        except IntegrityError as e:
            raise HTTPException(status_code=400, detail=f"Database error: {e}")


@app.get("/cases/{case_id}", response_model=Case)
async def get_case(
    case_id: str,
    expand: list[str] = Query(default=[]),
    handler: AsyncDbHandler = Depends(get_async_db_handler),
):
    async with async_engine.connect() as conn:
        case_obj = await handler.get_case(conn, case_id, expand=expand)
        if not case_obj:
            raise HTTPException(status_code=404, detail="Case not found")
        return case_obj


# Linking endpoints
@app.post("/cases/{case_id}/devices", status_code=status.HTTP_201_CREATED)
async def add_device_to_case(
    case_id: str, payload: CaseLinkDeviceRequest, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        try:
            await handler.link_device(conn, case_id, str(payload.item_id), payload.assigned_from)
            return await handler.get_case(conn, case_id, expand=["devices"])
        except ResourceConflictError as e:
            raise HTTPException(status_code=409, detail=e.message)
        except IntegrityError:
            raise HTTPException(status_code=404, detail="Device or case not found.")


@app.post("/cases/{case_id}/wearables", status_code=status.HTTP_201_CREATED)
async def add_wearable_to_case(
    case_id: str, payload: CaseLinkWearableRequest, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        try:
            await handler.link_wearable(conn, case_id, str(payload.item_id), payload.assigned_from)
            return await handler.get_case(conn, case_id, expand=["wearables"])
        except ResourceConflictError as e:
            raise HTTPException(status_code=409, detail=e.message)
        except IntegrityError:
            raise HTTPException(status_code=404, detail="Wearable or case not found.")


@app.post("/cases/{case_id}/contexts", status_code=status.HTTP_201_CREATED)
async def add_context_to_case(
    case_id: str, payload: CaseLinkContextRequest, handler: AsyncDbHandler = Depends(get_async_db_handler)
):
    async with async_engine.begin() as conn:
        try:
            await handler.link_context(conn, case_id, str(payload.context_id))
            # If context was already linked its just ignored and we return the case anyway
            return await handler.get_case(conn, case_id, expand=["contexts"])
        except IntegrityError:
            # should only happen if case or context dont exist
            raise HTTPException(status_code=404, detail="Context or case not found.")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
