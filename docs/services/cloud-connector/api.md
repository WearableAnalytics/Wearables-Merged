# API Endpoints

## Public/App Endpoints

Served on port 8000 locally and routed under `/cloud/*` in Kubernetes:

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Service health check |
| GET | `/providers` | None | List registered provider keys |
| GET | `/auth/{provider_name}/login` | None | Start OAuth 2.0 PKCE (`patient_id`, optional `redirect`, `redirect_uri`, `return_url`) |
| GET | `/callback` | None | OAuth callback (exchanges code, links patient, returns redirect/HTML or `?format=json`) |
| GET | `/auth/{provider_name}/callback` | None | Provider-scoped OAuth callback alias |
| GET | `/connections` | JWT | List linked accounts for the authenticated patient (optional `?provider=...`, tokens omitted) |
| POST | <code>/connections/{provider_name}<br>/{patient_id}/refresh</code> | JWT | Refresh stored OAuth access token |
| DELETE | <code>/connections/{provider_name}<br>/{patient_id}</code> | JWT | Deregister at provider and delete local link |
| POST | `/sync/{provider_name}` | JWT | Fetch provider data and publish to Kafka |
| POST | `/webhooks/{provider_name}` | None | Receive provider PUSH notifications |

## Cluster-Internal Admin Endpoints

Served on `INTERNAL_PORT` (8001), not exposed via Traefik:

- `GET /health`: Internal health probe
- `GET /connections` or `GET /internal/connections` (optional `?provider=...`): Read-only list of all patient links without tokens (via `kubectl port-forward`)

## Example Sync Request

If already OAuth-linked, `credentials` can be omitted (auto-lookup and token refresh run automatically):

```http
POST /sync/garmin
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "patient_id": "01a17e07-a10d-7a7c-aa23-2a0da2297b39",
  "credentials": {
    "token": "PROVIDER_ACCESS_TOKEN"
  }
}
```
