# Export pseudonymization verification

Verified locally on 2026-10-28. No deployment or push was performed.

## Results

- Complete extraction-service suite: **49 passed** (including export count and temporary-file lifecycle tests).
- Ruff check for the modified Python files: passed.
- HTTP integration tests use a real local TCP server serving synthetic NDJSON, the
  production `DbLordApi` HTTP client, and the extraction application's lifespan/routes.
- CSV and FHIR: duplicate readings remain deduplicated; patient pseudonyms are stable
  within a download, distinct across patients, and fresh across concurrent downloads.
- Original patient identifiers and additional identifying fields/tags are excluded.
- Missing patient identifiers remain missing; original source records are not mutated.
- Numeric values and timestamps survive a 2,000-reading CSV export.
- All bundled measurement types produce FHIR Observations with codes, values and unique
  resource IDs matching their Bundle entry URLs. This is not a full external FHIR validator.
- Unsupported types, free text, booleans and nonfinite numeric values are excluded.
- Filtering uses original patient IDs. Explicit opt-out matches the original response.
- OpenAPI exposes the boolean option; invalid boolean input returns HTTP 422.
- Deployment-specific and patient-specific FHIR mappings are not used in privacy mode.
- Exact response counters match CSV and FHIR bodies, including empty downloads, fully
  omitted datasets and mixed omission reasons. Duplicate copies are not counted as omissions.
- A 9 MiB prepared response rolls over to temporary disk storage and closes after
  delivery. Preparation errors and client disconnects also close the temporary file.

## Problems found and fixed during verification

The first allowlist incorrectly included mapping lookup keys such as `bpm` and `8867-4`
as measurement names. Four regression cases failed before correction and pass now.
The allowlist now uses only measurement-to-code mappings and is computed once per export.
The FHIR privacy renderer now loads the bundled mapping directly, independently of the
configurable ordinary export mapping.

## Reproduction

From the outer workspace directory, using the installed local environment:

```powershell
& ./.venv-export/Scripts/python.exe -m pytest -p no:cacheprovider Wearables-Merged-main/services/backend/extraction-service/tests -q
```

Alternatively, from this service directory with its development dependencies installed:

```sh
python -m pytest -p no:cacheprovider tests -q
```

## Limits

The real database, authentication flow, browser download and Kubernetes deployment were
not exercised. Docker and kubectl were unavailable, and no `DB_LORD_BASE_URL` environment
override was configured. The BFF proxy was reviewed statically: it forwards the original
query string and `Content-Disposition`/`Cache-Control` response headers.

The local environment used compatible packages installed from PyPI, not an exact
`uv.lock` synchronization. Dependency deprecation warnings remain (pytest-asyncio fixture
scope and Starlette/httpx TestClient). CI in the deployment's pinned environment remains
necessary before release.

Privacy mode deliberately omits unsupported/non-numeric measurements and arbitrary
metadata. Exact times and numeric values remain; this is pseudonymization, not anonymization.
No production data was used.
