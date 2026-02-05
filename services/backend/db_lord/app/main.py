from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import cases, contexts, devices, mapp_trees, mappings, patients, telemetry, wearables
from app.db.influx.client import client as influx_client
from app.db.postgres.engine import engine as pg_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    try:
        await influx_client.close()
    except Exception as e:
        print(f"Error closing InfluxDB: {e}")
    await pg_engine.dispose()


app = FastAPI(title="Wearables Backend", lifespan=lifespan)

app.include_router(patients.router, prefix="/patients", tags=["patients"])
app.include_router(cases.router, prefix="/cases", tags=["cases"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(wearables.router, prefix="/wearables", tags=["wearables"])
app.include_router(contexts.router, prefix="/contexts", tags=["contexts"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(mappings.router, prefix="/mappings", tags=["mappings"])
app.include_router(mapp_trees.router, prefix="/map_trees", tags=["map_trees"])
