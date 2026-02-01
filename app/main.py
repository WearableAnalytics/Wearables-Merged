import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Depends
from .models import IngestPayload, IngestResponse
from .kafka_producer import get_producer
from datetime import datetime

logger = logging.getLogger(__name__)

_kafka_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kafka_send")

app = FastAPI(title="Wearables Import Service", version="0.9.0")

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

def _send_to_kafka_sync(producer, kafka_msg):
    try:
        producer.produce_measurements(kafka_msg)
    except Exception as e:
        logger.error("Failed to send to Kafka in background: %s", e)

@app.post("/ingest", response_model=IngestResponse)
async def ingest(payload: IngestPayload, producer=Depends(get_producer)):
    kafka_msg = [payload.model_dump(mode='json')]

    loop = asyncio.get_running_loop()
    loop.run_in_executor(_kafka_executor, _send_to_kafka_sync, producer, kafka_msg)

    return IngestResponse(
        total_messages_produced=len(kafka_msg),
        instantaneous_count=len(payload.measurements.instantaneous),
        cumulative_count=len(payload.measurements.cumulative),
        duration_count=len(payload.measurements.duration),
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
