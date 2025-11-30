from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from kafka import errors as kafka_errors
from .models import IngestPayload, IngestResponse
from .kafka_producer import get_producer
from .influx_writer import get_influx_writer
from datetime import datetime
# from .security import verify_token

app = FastAPI(title="Wearables Import Service", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/ingest", response_model=IngestResponse)
async def ingest(payload: IngestPayload, producer=Depends(get_producer), influx_writer=Depends(get_influx_writer)):
    kafkaMsg = [payload.model_dump(mode='json')]
    
    messages = []
    
    # Instantaneous
    for m in payload.measurements.instantaneous:
        messages.append({
            "category": "instantaneous",
            "type": m.type,
            "value": m.value,
            "unit": m.unit,
            "timestamp": m.timestamp.isoformat(),
            "deviceId": payload.deviceInfo.deviceId,
            "platform": payload.deviceInfo.platform,
            "batchCollectionStart": payload.batchInfo.collectionStart.isoformat(),
            "batchCollectionEnd": payload.batchInfo.collectionEnd.isoformat(),
            "sourceName": payload.sourceName,
            "ingestTimestamp": payload.timestamp.isoformat(),
        })
    
    # Cumulative
    for m in payload.measurements.cumulative:
        messages.append({
            "category": "cumulative",
            "type": m.type,
            "value": m.value,
            "unit": m.unit,
            "periodStart": m.periodStart.isoformat(),
            "periodEnd": m.periodEnd.isoformat(),
            "durationSeconds": m.duration,
            "deviceId": payload.deviceInfo.deviceId,
            "platform": payload.deviceInfo.platform,
            "batchCollectionStart": payload.batchInfo.collectionStart.isoformat(),
            "batchCollectionEnd": payload.batchInfo.collectionEnd.isoformat(),
            "sourceName": payload.sourceName,
            "ingestTimestamp": payload.timestamp.isoformat(),
        })
    
    # Duration
    for m in payload.measurements.duration:
        messages.append({
            "category": "duration",
            "type": m.type,
            "value": m.value,
            "unit": m.unit,
            "startTime": m.startTime.isoformat(),
            "endTime": m.endTime.isoformat(),
            "durationMinutes": m.durationMinutes,
            "deviceId": payload.deviceInfo.deviceId,
            "platform": payload.deviceInfo.platform,
            "batchCollectionStart": payload.batchInfo.collectionStart.isoformat(),
            "batchCollectionEnd": payload.batchInfo.collectionEnd.isoformat(),
            "sourceName": payload.sourceName,
            "ingestTimestamp": payload.timestamp.isoformat(),
        })

    try:
        # Send to Kafka
        total = producer.produce_measurements(kafkaMsg)
    except kafka_errors.NoBrokersAvailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Kafka brokers unavailable")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed sending to Kafka: {str(e)}")
    
    try:
        # Write to InfluxDB
        influx_writer.write_measurements(messages)
    except Exception as e:
        # Log but don't fail the request if InfluxDB write fails
        import logging
        logging.error(f"Failed to write to InfluxDB: {e}", exc_info=True)
        # Continue - Kafka write was successful

    return IngestResponse(
        total_messages_produced=total,
        instantaneous_count=len(payload.measurements.instantaneous),
        cumulative_count=len(payload.measurements.cumulative),
        duration_count=len(payload.measurements.duration),
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
