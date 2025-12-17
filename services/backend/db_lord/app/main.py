from os import abort
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Query, HTTPException
from flask import jsonify

from app.db import async_engine

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "OK"}



@app.get("/patients/{patient_id}")
async def get_patient_endpoint(patient_id: str):
    async with async_engine.connect() as conn:
        patient = await get_patient(conn=conn, patient_id=patient_id)

    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    return jsonify(patient)

@app.get("/wearables/{wearable_id}")
async def get_wearable_endpoint(wearable_id: str):
    async with async_engine.connect() as conn:
        wearable = await get_wearable(conn=conn, wearable_id=wearable_id)

    if wearable is None:
        raise HTTPException(status_code=404, detail="Wearable not found")

    return jsonify(wearable)

@app.get("/devices/{device_id}")
async def get_devices_endpoint(device_id: str):
    async with async_engine.connect() as conn:
        device = await get_device(conn=conn, device_id=device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return jsonify(device)

@app.get("/contexts/{context_id}")
async def get_context_endpoint(context_id: str):
    async with async_engine.connect() as conn:
        context = await get_context(conn=conn, context_id=context_id)

    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")

    return jsonify(context)

@app.get("/cases/{case_id}")
async def get_cases_endpoint(case_id: str):
    async with async_engine.connect() as conn:
        case = await get_case(conn=conn, case_id=case_id)

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return jsonify(case)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)