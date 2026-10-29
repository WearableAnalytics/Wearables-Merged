import logging
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends

from .models import SyncRequest, SyncResponse
from .providers import get_provider, list_available_providers
from .kafka_publisher import get_publisher, CloudKafkaPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Wearables Cloud Connector Service",
    description="Modular multi-provider cloud telemetry connector for the Wearables platform",
    version="1.0.0",
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "wearables-cloud-connector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/providers")
async def get_providers():
    return {
        "available_providers": list_available_providers(),
    }


@app.post("/sync/{provider_name}", response_model=SyncResponse)
async def sync_provider(
    provider_name: str,
    request: SyncRequest,
    publisher: CloudKafkaPublisher = Depends(get_publisher),
):
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    is_valid = await provider.validate_credentials(request.credentials)
    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid credentials or token for provider '{provider_name}'",
        )

    try:
        payload = await provider.fetch_telemetry(
            patient_id=request.patient_id,
            credentials=request.credentials,
            start_time=request.start_time,
            end_time=request.end_time,
        )
    except Exception as e:
        logger.error("Error fetching telemetry from %s: %s", provider_name, e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Failed to fetch data from {provider_name}: {e}")

    payload_dict = payload.model_dump(mode="json")
    published = publisher.publish_payload(payload_dict)

    return SyncResponse(
        provider=provider_name,
        patient_id=request.patient_id,
        status="success",
        instantaneous_count=len(payload.measurements.instantaneous),
        cumulative_count=len(payload.measurements.cumulative),
        duration_count=len(payload.measurements.duration),
        waveform_count=len(payload.measurements.waveforms),
        published_to_kafka=published,
        timestamp=datetime.now(timezone.utc),
    )


@app.post("/webhooks/{provider_name}")
async def provider_webhook(
    provider_name: str,
    data: dict,
    publisher: CloudKafkaPublisher = Depends(get_publisher),
):
    """Receives asynchronous push notifications or webhooks from any registered cloud provider"""
    try:
        get_provider(provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("Received push webhook from provider '%s'", provider_name)
    return {
        "status": "accepted",
        "provider": provider_name,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
