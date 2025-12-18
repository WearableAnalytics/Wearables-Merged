import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.exc import IntegrityError
from starlette import status
from starlette.responses import JSONResponse

from app.db import async_engine
from db_handler import AsyncDbHandler, get_async_db_handler
from models.sql_schema import PatientBase, Patient, Wearable, DeviceBase, Device, Context, ContextBase

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "OK"}


@app.post(
    "/patients",
    response_model=Patient,
    status_code=status.HTTP_201_CREATED,
)
async def post_patients(
        payload: PatientBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
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
async def get_patient_endpoint(
        patient_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
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
        patient_id: str,
        payload: PatientBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        patient = await handler.update_patient(conn=conn, patient_id=patient_id, patient_data=payload)

        if patient is not None:
            return patient

        try:
            patient = await handler.create_patient(conn=conn, patient_data=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Patient already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=patient)


@app.delete(
    "/patients/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_patient_endpoint(
        patient_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_patient(conn=conn, patient_id=patient_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Patient cannot be deleted due to conflicts")

        if not deleted:
            raise HTTPException(status_code=404, detail="Patient not found")


@app.get(
    "/wearables/{wearable_id}",
    response_model=Wearable,
    status_code=status.HTTP_200_OK,
)
async def get_wearable_endpoint(
        wearable_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
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
        payload: DeviceBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            wearable = await handler.create_wearable(conn=conn, wearable_base=payload)
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
        wearable_id: str,
        payload: DeviceBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        wearable = await handler.update_wearable(conn=conn, wearable_id=wearable_id, wearable_base=payload)

        if wearable is not None:
            return wearable

        try:
            wearable = await handler.create_wearable(conn=conn, wearable_base=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Wearable already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=wearable)

@app.delete(
    "/wearables/{wearable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_wearable_endpoint(
        wearable_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_wearable(conn=conn, wearable_id=wearable_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Wearable not found")

        if not deleted:
            raise HTTPException(status_code=404, detail="Wearable not found")


@app.get(
    "/devices/{device_id}",
    response_model=Device,
    status_code=status.HTTP_200_OK,
)
async def get_devices_endpoint(
        device_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.connect() as conn:
        device = await handler.get_device(conn=conn, device_id=device_id)

        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

        return device

@app.post(
    "/devices",
    response_model=Device,
    status_code=status.HTTP_201_CREATED
)
async def post_devices_endpoint(
        payload: DeviceBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
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
        device_id: str,
        payload: DeviceBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        device = await handler.update_device(conn=conn, device_id=device_id, device_base=payload)

        if device is not None:
            return device

        try:
            device = await handler.create_device(conn=conn, device_base=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Device already exists")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=device)


@app.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_devices_endpoint(
        device_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_device(conn=conn, device_id=device_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Device cannot be deleted due to conflict")

        if not deleted:
            raise HTTPException(status_code=404, detail="Device not found")



@app.get(
    "/contexts/{context_id}",
    response_model=Context,
    status_code=status.HTTP_200_OK,
)
async def get_context_endpoint(
        context_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
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
async def post_context_endpoint(
        payload: ContextBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
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
        context_id: str,
        payload: ContextBase,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        context = await handler.update_context(conn=conn, context_id=context_id, context_base=payload)

        if context is not None:
            return context

        try:
            context = await handler.create_context(conn=conn, context_base=payload)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Cannot update context due to conflict")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return JSONResponse(status_code=status.HTTP_201_CREATED, content=context)

@app.delete(
    "/contexts/{context_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_context_endpoint(
        context_id: str,
        handler: AsyncDbHandler = Depends(get_async_db_handler)):
    async with async_engine.begin() as conn:
        try:
            deleted = await handler.delete_context(conn=conn, context_id=context_id)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Cannot delete context due to conflict")

        if not deleted:
            raise HTTPException(status_code=404, detail="Context not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
