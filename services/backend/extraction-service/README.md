# extraction-service

Researcher-facing Extraction API. Reads telemetry from `db_lord` and exports it.

## Endpoints
- `GET /v1/measurements/types`: measurement types stored in Influx
- `GET /v1/measurements`: paged JSON, newest first (follow `next_end` until `has_more` is false)
- `GET /v1/measurements/export.csv`: streaming CSV
- `GET /v1/measurements/export.fhir`: streaming FHIR `collection` Bundle of Observations
- `GET /docs`: Swagger UI, `GET /openapi.json`: OpenAPI document

All data endpoints take `measurement`, `patient_id`, `start` and `end`, all optional.
- `start` defaults to 2020-01-01. db_lord on its own only reads the last 24h.
- `patient_id` is the db-lord patient id. Influx stores it as the `device-id` tag and as
  `device-id-reference=Patient/<id>`. Older points have only one of the two, so both are queried.
- The same reading can be stored more than once (one copy per Telegraf pod that ingested it,
  told apart only by the `host` tag). Copies are removed from every response.
- FHIR uses the point's `mapping_id` mapping from db_lord when it has one, otherwise
  `src/app/default_fhir_mapping.yaml` (a copy of the mapper-validator mapping in
  `gitops/apps/services/mapper-validator/templates/mappings-config-map.yaml`; keep them in sync).

## Access
The service has no auth of its own and is only reachable in the cluster. The Wearables BFF serves it
at `/api/extraction` (set `EXTRACTION_API_URL` on the BFF) for logged-in researchers and admins, or
with the researcher API token from the web app's API Access page as `Authorization: Bearer <token>`.
The Swagger UI is then at `/api/extraction/docs`.

## Configuration
Environment variables:
- `DB_LORD_BASE_URL` (default: `http://db-lord:8000`)
- `ROOT_PATH`: prefix the BFF serves the API under (`/api/extraction`), used by the Swagger UI
- `DEFAULT_START`, `PATIENT_WINDOW`, `DB_LORD_TIMEOUT_SECONDS`, `FHIR_DEFAULT_MAPPING_PATH`: see `src/app/settings.py`

## Run and test
`uv run uvicorn src.app.main:app --reload --port 8010`

`uv run pytest`
