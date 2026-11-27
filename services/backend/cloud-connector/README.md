# Wearables Cloud Connector

Ingests health telemetry from external wearable cloud APIs (OAuth 2.0 linking, token refresh, webhooks, and REST sync) and publishes standardized `IngestPayload` messages to Kafka.  It also fetches potentially more data than mobile aggregators can provide.

Full service docs (including provider limits and overview): [Wearables Docs - Cloud Connector](https://wearableanalytics.github.io/Wearables-Merged/services/cloud-connector/)

Swagger & ReDoc: `/docs` and `/redoc` locally, or `/cloud/docs` and `/cloud/redoc` in the cluster (`ENABLE_DOCS=true`).

## Data Flow

```text
Cloud Provider APIs/Webhooks -> Cloud Connector -> Kafka (wearables-raw) -> FHIR Mapper -> Kafka (wearables-lp) -> Telegraf -> InfluxDB
```

## Implemented Providers

Registered in [app/providers/__init__.py](app/providers/__init__.py):

| Provider Key | Ecosystem | Auth Flow | Sync & Webhooks |
|---|---|---|---|
| `garmin` | [Garmin Connect](https://developer.garmin.com/gc-developer-program/overview/) | OAuth 2.0 PKCE | PUSH webhooks (primary) + REST backfill or `mock_data` |
| `polar` | [Polar AccessLink v3](https://www.polar.com/accesslink-api/#polar-accesslink-api) | OAuth 2.0 + user registration | REST sync (webhooks logged only) |
| `google_health` | [Google Health](https://developers.google.com/health) (Fitbit, Pixel Watch & Health Connect) | OAuth 2.0 PKCE | REST sync (Pub/Sub pings logged only) |
| `oura` | [Oura Ring v2](https://cloud.ouraring.com/v2/docs/) | OAuth 2.0 PKCE | REST sync (webhooks logged only) |
| `whoop` | [WHOOP v2](https://developer.whoop.com/api) | OAuth 2.0 PKCE | REST sync + v2 webhook parsing |
| `withings` | [Withings Health](https://developer.withings.com/) | OAuth 2.0 PKCE | REST sync (webhooks logged only) |

Credentials use `<PROVIDER>_CLIENT_ID` and `<PROVIDER>_CLIENT_SECRET`

## Project Structure

- [app/main.py](app/main.py): FastAPI routes, OAuth flow, webhooks and Kafka sync
- [app/providers/base.py](app/providers/base.py): `BaseCloudProvider` interface
- [app/providers/__init__.py](app/providers/__init__.py): Provider registry
- [app/models.py](app/models.py): `SyncRequest`, `SyncResponse` and `IngestPayload` models
- [app/security.py](app/security.py): Case verification JWT validation (HS256)
- [app/storage.py](app/storage.py): JSON-backed `ConnectionStore` for OAuth links and PKCE state
- [app/kafka_publisher.py](app/kafka_publisher.py): Kafka producer for `wearables-raw`
- [app/internal_server.py](app/internal_server.py): Cluster-internal admin server on `INTERNAL_PORT` (8001)
- [app/config.py](app/config.py): Environment settings

## API Endpoints

Public endpoints run on port 8000 (`/cloud/*` in the cluster):

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Service health check |
| GET | `/providers` | None | List registered provider keys |
| GET | `/auth/{provider_name}/login` | None | Start OAuth 2.0 PKCE flow (`patient_id`, optional `redirect`, `redirect_uri`, `return_url`) |
| GET | `/callback` | None | OAuth callback (exchanges code, links patient, returns redirect/HTML or `?format=json`) |
| GET | `/auth/{provider_name}/callback` | None | Provider-scoped OAuth callback alias |
| GET | `/connections` | Case JWT | List linked accounts for the authenticated patient |
| POST | <code>/connections/{provider_name}<br>/{patient_id}/refresh</code> | Case JWT | Refresh stored OAuth access token |
| DELETE | <code>/connections/{provider_name}<br>/{patient_id}</code> | Case JWT | Deregister at provider and delete local link |
| POST | `/sync/{provider_name}` | Case JWT | Fetch provider telemetry and publish to Kafka |
| POST | `/webhooks/{provider_name}` | None | Receive provider PUSH notifications |

Cluster-internal admin endpoints on port 8001 (not exposed via Traefik):
- `GET /health`
- `GET /connections` or `GET /internal/connections` (all patient links without tokens, via `kubectl port-forward`)

Example sync request (if already OAuth-linked, `credentials` can be omitted):

```http
POST /sync/garmin
Authorization: Bearer <case-verification-jwt>
Content-Type: application/json

{
  "patient_id": "01a17e07-a10d-7a7c-aa23-2a0da2297b39",
  "credentials": {
    "token": "PROVIDER_ACCESS_TOKEN"
  }
}
```

## Configuration

All environment variables are listed in [.env.example](.env.example), [app/config.py](app/config.py), and the [Helm chart](../../../gitops/apps/services/cloud-connector/values.yaml):

- `PUBLIC_BASE_URL` and `OAUTH_REDIRECT_URI`: Base URL and OAuth callback (for example `http://localhost/cloud/callback` locally or `https://wearables.charite.de/cloud/callback` in the cluster)
- `JWT_SECRET` and `JWT_ISSUER`: Must match `wearables-bff` for JWT-protected routes
- `CLOUD_CONNECTOR_STORAGE_PATH`: Path to persistent JSON connection store (default `/data/connections.json`)
- `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_TOPIC`: Target Kafka broker and raw topic (`wearables-raw`)

## Local Development & Tests

```bash
cd services/backend/cloud-connector
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pytest -q tests/
```

For local webhook testing, it is recommended to set up a `cloudflared` tunnel to expose the local webhook endpoint to the internet.
