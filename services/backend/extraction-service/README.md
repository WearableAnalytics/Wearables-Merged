# extraction-service

Researcher-facing Extraction API.

## What it does
- Calls `db_lord` telemetry endpoint to retrieve measurements.
- Exposes researcher-friendly endpoints:
  - `GET /v1/measurements` (paged JSON)
  - `GET /v1/measurements/export.csv` (streaming CSV)

## Measurement types
`db_lord` accepts `measurement` as a free-form string (it is not enumerated in the current codebase).

Known examples from the legacy `db_lord` OpenAPI spec (`services/backend/db_lord/old_code/api.yaml`):
- `spo2`
- `heart-rate`

If you want an authoritative list, we should either:
- query InfluxDB schema (list distinct `_measurement` values), or
- maintain an explicit registry (enum/table) and validate at ingestion.

## Configuration
Environment variables:
- `DB_LORD_BASE_URL` (default: `http://db-lord:8000`)

## Run
Use any ASGI server; example with uvicorn:

`uvicorn extraction_service.main:app --reload --port 8010`
