from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import cases, contexts, devices, patients, telemetry, wearables
from app.db.influx.client import client as influx_client
from app.db.postgres.engine import engine as pg_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # await influx_client.close()
    await pg_engine.dispose()


app = FastAPI(title="Wearables Backend", lifespan=lifespan)

app.include_router(patients.router, prefix="/patients", tags=["patients"])
app.include_router(cases.router, prefix="/cases", tags=["cases"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(wearables.router, prefix="/wearables", tags=["wearables"])
app.include_router(contexts.router, prefix="/contexts", tags=["contexts"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
