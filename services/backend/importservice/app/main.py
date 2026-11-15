"""Durable upload acceptance. A 202 receipt means archived, not yet processed."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import get_settings
from .contracts import Conflict, parse_upload
from .crypto import ArchiveCipher
from .metrics import MetricsMiddleware, start_metrics_server
from .models import IngestPayload
from .pipeline import KafkaGateway
from .repository import QuotaExceeded, Repository
from .security import verify_case_verification_token
from .worker import Worker


class AdmissionMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings, self.active = app, settings, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].startswith("/ingest"):
            return await self.app(scope, receive, send)
        if self.active >= self.settings.max_inflight:
            return await JSONResponse({"detail": "Upload capacity reached"}, 503)(scope, receive, send)
        self.active += 1
        body = bytearray()
        try:
            try:
                async with asyncio.timeout(10):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > self.settings.max_body_bytes:
                            return await JSONResponse({"detail": "Upload body exceeds the configured limit"}, 413)(
                                scope, receive, send
                            )
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await JSONResponse({"detail": "Upload body timeout"}, 408)(scope, receive, send)
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, buffered_receive, send)
        finally:
            self.active -= 1


def get_repository(request: Request):
    repository = getattr(request.app.state, "repository", None)
    if repository is None:
        raise HTTPException(503, "Upload archive is unavailable")
    return repository


def create_app(settings=None):
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application):
        settings.validate()
        repository = Repository(settings, ArchiveCipher(settings))
        gateway = None
        try:
            await repository.open()
            gateway = KafkaGateway(settings)
            worker = Worker(repository, gateway, settings)
            application.state.repository = repository
            start_metrics_server()
            task = asyncio.create_task(worker.run())
            try:
                yield
            finally:
                application.state.repository = None
                worker.stop.set()
                await task
        finally:
            if gateway:
                await gateway.close()
            await repository.close()

    application = FastAPI(title="Wearables Import Service", version="1.0.0", lifespan=lifespan)
    application.add_middleware(MetricsMiddleware)
    application.add_middleware(AdmissionMiddleware, settings=settings)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse({"detail": "Invalid upload structure"}, 422)

    @application.get("/health")
    async def health():
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    @application.get("/ready")
    async def ready(repository=Depends(get_repository)):
        try:
            async with repository.pool.connection() as connection:
                await connection.execute("SELECT 1")
        except Exception as exc:
            raise HTTPException(503, "Upload archive is unavailable") from exc
        return {"status": "ok", "acceptanceGuarantee": "postgres-archive"}

    @application.post("/ingest", status_code=202)
    async def ingest(
        request: Request,
        payload: IngestPayload,
        claims=Depends(verify_case_verification_token),
        repository=Depends(get_repository),
    ):
        try:
            upload = parse_upload(await request.body(), claims, request.headers.get("idempotency-key"), settings)
            upload_id, replayed = await repository.accept(upload)
            receipt = await repository.receipt(upload_id, claims)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, "Invalid upload contract") from exc
        except Conflict as exc:
            raise HTTPException(409, "An immutable upload key or source record changed") from exc
        except QuotaExceeded as exc:
            raise HTTPException(429, "Participant upload budget reached", headers={"Retry-After": "3600"}) from exc
        except Exception as exc:
            raise HTTPException(503, "Upload archive is unavailable; retry with the same bytes and key") from exc
        return {
            **receipt,
            "replayed": replayed,
            "instantaneous_count": len(payload.measurements.instantaneous),
            "cumulative_count": len(payload.measurements.cumulative),
            "duration_count": len(payload.measurements.duration),
        }

    @application.get("/ingest/{upload_id}")
    async def receipt(
        upload_id: UUID, claims=Depends(verify_case_verification_token), repository=Depends(get_repository)
    ):
        try:
            result = await repository.receipt(str(upload_id), claims)
        except Exception as exc:
            raise HTTPException(503, "Upload journal is unavailable") from exc
        if result is None:
            raise HTTPException(404, "Upload not found")
        return result

    @application.post("/ingest/{upload_id}/retry")
    async def retry(
        upload_id: UUID, claims=Depends(verify_case_verification_token), repository=Depends(get_repository)
    ):
        try:
            count = await repository.retry(str(upload_id), claims)
        except Exception as exc:
            raise HTTPException(503, "Upload journal is unavailable") from exc
        if count is None:
            raise HTTPException(404, "Upload not found")
        return {"retriedCount": count}

    return application


app = create_app()
