# Tests README

GitHub Copilot was used extensively to assist in writing these tests; however, behavior and correctness were obviosuly verified manually though.

## Directory layout

- `tests/unit/`
  Fast tests using SQLite and mocked InfluxDB
- `tests/integration/`
  Real dependency tests using testcontainers (`postgres:18` + InfluxDB)
- `tests/smoke/`
  Minimal startup/health/lifespan style checks
- `tests/perf/`
  Manual telemetry read benchmarks
- `tests/helpers/`
  Shared assertion and API helper functions
- `tests/fixtures/`
  Fixture modules split by concern
- `tests/conftest.py`
  Thin plugin loader + folder-based marker assignment

## Running tests

Prerequisites:

- Python env installed via `uv`
- Docker running (required for integration tests)


- full suite:
  - `uv run pytest -q`
- full suite in parallel:
  - `uv run pytest -n <4/auto> -q`
- unit + smoke only:
  - `uv run pytest -m "not integration" -q`
- integration only:
  - `uv run pytest -m integration -q`
- manual perf benchmark:
  - `uv run pytest tests/perf/test_telemetry_read_perf.py --run-perf -s -q`

## Markers and async style

- folder markers are auto-applied in `tests/conftest.py`
  - `tests/unit/*` -> `@pytest.mark.unit`
  - `tests/integration/*` -> `@pytest.mark.integration`
  - `tests/smoke/*` -> `@pytest.mark.smoke`
- async tests should use `@pytest.mark.anyio`

## Fixture architecture

- `tests/fixtures/db.py`
  - SQLite engine/session for unit scope
  - PostgreSQL testcontainer + Alembic schema for integration scope
  - transaction/savepoint isolation
- `tests/fixtures/influx.py`
  - mocked Influx client/repo for unit scope
  - real Influx testcontainer client/repo for integration scope
- `tests/fixtures/app.py`
  - app/client fixtures with dependency overrides
  - GraphQL context/session wiring
- `tests/fixtures/factories.py`
  - data builders for entities and assignments
  - payload-style and ORM-style variants

## Factory conventions

- `*_factory`
  returns payload-shaped dicts for unit tests and focused DB-backed setup.
- `*_orm_factory`
  returns ORM instances for repo/service tests.

Use API helpers from `tests/helpers/api.py` for integration setup when the test verifies endpoint, GraphQL, or system behavior.
Use DB factories when the setup is unit/repo-level or not exposed through public endpoints.
Use ORM factories when identity map, flush/commit behavior, or relationships are the test subject.

## Assertion conventions

Use helpers from `tests/helpers/api.py` instead of ad-hoc assertions:

- `assert_json_response(...)`
- `assert_api_error(...)`
- `assert_graphql_ok(...)`
- `assert_graphql_error(...)`
- `assert_no_content(...)`

## Integration

- real databases
- real HTTP/GraphQL transports
- test harness controls app wiring and environment

## Troubleshooting

- integration tests fail with Docker errors:
  - ensure Docker daemon is running
- Alembic migration errors in integration setup:
  - run `uv run pytest -m integration -q` to reproduce in isolation
- GraphQL failures:
  - first validate HTTP response with `assert_graphql_ok/assert_graphql_error`
- flaky telemetry visibility:
  - use polling helper patterns already used in integration tests (`eventually`)

## Performance tests

- `tests/perf/test_telemetry_read_perf.py` is the manual sequential benchmark for telemetry read paths
- it prints:
  - a short human-readable timing summary
- it covers:
  - REST structured page reads
  - GraphQL structured page reads
  - REST raw page reads
  - REST raw page reads filtered to `heart_rate`
  - REST raw page streaming
  - full structured/raw window scans
  - full structured/raw streaming
- telemetry reads now use window semantics:
  - request `limit`
  - response `has_more`
  - follow-up with response `next_end` as the next request `end`
- perf tests are skipped unless `--run-perf` is passed
