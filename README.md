# Wearables Import Service

FastAPI service that ingests batched wearable measurements and publishes individual measurement records to a Kafka topic.

## Features
- Validates incoming JSON payload with Pydantic models.
- Splits batch into individual measurement messages (instantaneous, cumulative, duration).
- Publishes each measurement to Kafka (`wearables-raw`).
- Health check endpoint at `/health`.
- Ingestion endpoint at `/ingest` returns counts and topic.

## Configuration
Environment variables (or `.env` file):
```
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=wearables-raw
KAFKA_CLIENT_ID=import-service
```

## Installation
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Sample Payload
```json
{
  "deviceInfo": {
    "platform": "iOS",
    "deviceId": "unknown_device",
  },
  "batchInfo": {
    "collectionStart": "2025-11-17T18:53:55.034548",
    "collectionEnd": "2025-11-18T00:53:55.034548"
  },
  "measurements": {
    "instantaneous": [],
    "cumulative": [
      {
        "type": "STEPS",
        "value": 34,
        "unit": "COUNT",
        "periodStart": "2025-11-17T22:11:26.462",
        "periodEnd": "2025-11-17T22:12:15.033",
        "duration": 48
      },
      {
        "type": "ACTIVE_ENERGY_BURNED",
        "value": 0.6739999999999999,
        "unit": "KILOCALORIE",
        "periodStart": "2025-11-17T22:11:23.906",
        "periodEnd": "2025-11-17T22:12:15.029",
        "duration": 51
      }
    ],
    "duration": []
  },
  "sourceName": "Jakobs iPhone",
  "totalStepsToday": null,
  "timestamp": "2025-11-18T00:53:55.861405"
}
```

## Producing Logic
Each measurement produces a JSON message with common batch/device metadata plus measurement-specific fields.

## Next Steps
- Add authentication / token validation.
- Add error metrics and retry/backoff logic.
