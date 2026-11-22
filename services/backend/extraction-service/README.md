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

## Pseudonymized output

Who gets what depends on the caller's roles (see Access):

| Caller | Output |
|---|---|
| admin or practitioner (also when they are a researcher too) | original data; `pseudonymize=true` opts in |
| researcher | always pseudonymized, `pseudonymize=false` is ignored |

This covers `/v1/measurements/export.csv`, `/v1/measurements/export.fhir` and the paged
`/v1/measurements`. `/v1/measurements/reconciled` is not available to researchers (403): it needs the
real patient id and returns source details (writer, name, device). Each response uses fresh random patient UUIDs, consistent
within that response. Different downloads (including CSV versus FHIR) cannot be
joined using these UUIDs. The mapping exists only in request memory and is not saved.
Filtering still uses the original patient ID. Missing patient IDs remain missing.

This restricted mode includes only finite numeric `value` measurements known to the
bundled FHIR mapping. Unknown measurement types and nonnumeric values are omitted.
Extra fields, raw tags, device information and individual FHIR mappings are excluded;
FHIR uses the bundled mapping and fresh Observation IDs. CSV's `fields` column is empty.
The filenames contain `pseudonymized`, and downloads use `Cache-Control: no-store`.

Privacy downloads report exact counts in `X-Export-Considered`, `X-Export-Exported`,
`X-Export-Omitted`, `X-Export-Omitted-Unsupported` and `X-Export-Omitted-Invalid-Value`
response headers. Counts refer to filtered readings **after deduplication**. A reading
with an unknown type is counted as unsupported even if its value is also invalid.
When readings are omitted, the filename includes the count, for example
`measurements-pseudonymized-2-omitted.csv`. CSV/FHIR bodies keep their existing format.

To report counts for the actual download, privacy mode prepares the complete export
before sending response headers. Up to 8 MiB is buffered in memory; larger bodies use
an automatically closed temporary file. Downloads therefore start after preparation
and require sufficient temporary disk space. Ordinary exports still stream directly.
The BFF forwards these counters. The local `demo_export.py` page displays the totals
and reasons; the production web UI has not yet been extended to display them.

This is pseudonymization, **not anonymization**: exact timestamps and measurement
values remain, and may still allow identification through other data. On the paged JSON API
every page gets its own pseudonyms, so pages cannot be joined by patient (use the CSV or FHIR
export for that); the counters are not sent there. Stored measurements are not modified.

## Access
The Wearables BFF serves the service at `/api/extraction` (set `EXTRACTION_API_URL` on the BFF) for
logged-in admins, practitioners and researchers, or with a researcher's or admin's personal API token
created on the web app's API Access page as `Authorization: Bearer <token>`. The Swagger UI is then at
`/api/extraction/docs`.

The BFF checks the session or token, then forwards the caller as a short-lived HS256 JWT in the
`X-Extraction-Principal` header, signed with `EXTRACTION_INTERNAL_JWT_SECRET` (`src/app/auth.py`).
Claims: `sub` (email), `roles` (`admin`, `researcher`, `practitioner`), `auth` (`session` or
`api_token`), `token_id`, `aud=extraction-service`, `exp` (60s).
Every `/v1` route checks it again before reading any data:
- no or invalid principal: 401; secret not configured: 503
- roles without `admin`, `practitioner` or `researcher` (`EXPORT_ROLES`): 403

Callers without a role in `RAW_EXPORT_ROLES` get pseudonymized output (see above). The checked caller
is also on `request.state.principal`.
`/health`, `/docs`, `/redoc` and `/openapi.json` need no principal.

## Configuration
Environment variables:
- `DB_LORD_BASE_URL` (default: `http://db-lord:8000`)
- `ROOT_PATH`: prefix the BFF serves the API under (`/api/extraction`), used by the Swagger UI
- `EXTRACTION_INTERNAL_JWT_SECRET`: shared with the BFF, required (see Access). In Kubernetes it is in
  `extraction-service-secrets`, written by `scripts/bootstrap-runtime-secrets.sh` (production) or
  `gitops/local/setup-local.sh` (Minikube)
- `EXPORT_ROLES` (default: `["admin","practitioner","researcher"]`), `RAW_EXPORT_ROLES` (default:
  `["admin","practitioner"]`)
- `DEFAULT_START`, `PATIENT_WINDOW`, `DB_LORD_TIMEOUT_SECONDS`, `FHIR_DEFAULT_MAPPING_PATH`: see `src/app/settings.py`

## Run and test
```bash
ROOT_PATH=/api/extraction \
EXTRACTION_INTERNAL_JWT_SECRET=<same as the BFF's> \
DB_LORD_OPERATOR_TOKEN=<DATABASE_OPERATOR_TOKEN from deploy/local/.env> \
DB_LORD_BASE_URL=http://localhost:8000 \
uv run uvicorn src.app.main:app --reload --port 8010
```

Then open the Swagger UI through the BFF at http://localhost:3001/api/extraction/docs, logged in as an
admin, practitioner or researcher. `EXTRACTION_INTERNAL_JWT_SECRET` must match the BFF's
(`services/backend/wearables-bff/.env`); without `ROOT_PATH` the page fails with "Failed to load API definition".

`uv run pytest`
