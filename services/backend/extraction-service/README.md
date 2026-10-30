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

## Optional pseudonymized downloads

Add `pseudonymize=true` to either file export endpoint:

- `/v1/measurements/export.csv?pseudonymize=true`
- `/v1/measurements/export.fhir?pseudonymize=true`

The default is `false`. Each download uses fresh random patient UUIDs, consistent
within that download. Different downloads (including CSV versus FHIR) cannot be
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
values remain, and may still allow identification through other data. The paged JSON
API is unchanged. This option does not modify stored measurements or access controls.

## Access
The service has no auth of its own and is only reachable in the cluster. The Wearables BFF serves it
at `/api/extraction` (set `EXTRACTION_API_URL` on the BFF) for logged-in researchers and admins, or
with a personal API token created on the web app's API Access page as `Authorization: Bearer <token>`.
The Swagger UI is then at `/api/extraction/docs`.

## Configuration
Environment variables:
- `DB_LORD_BASE_URL` (default: `http://db-lord:8000`)
- `ROOT_PATH`: prefix the BFF serves the API under (`/api/extraction`), used by the Swagger UI
- `DEFAULT_START`, `PATIENT_WINDOW`, `DB_LORD_TIMEOUT_SECONDS`, `FHIR_DEFAULT_MAPPING_PATH`: see `src/app/settings.py`

## Run and test
`uv run uvicorn src.app.main:app --reload --port 8010`

`uv run pytest`
