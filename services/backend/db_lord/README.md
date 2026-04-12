# db-lord

Backend service for managing wearable domain entities and telemetry.

- REST API (FastAPI)
- GraphQL API (Strawberry)
- PostgreSQL 18 for relational/domain data
- InfluxDB 2.7 for telemetry time-series data

## What This Service Does

- Manages patients, cases, devices, wearables, contexts.
- Allows users to query telemetry data.
- Tracks temporal assignments between cases and hardware.
- Stores FHIR mappings and dot dependency files needed to map stored telemetry data to FHIR format.
- Exposes GraphQL with nested Relay connections and subscriptions.

## Architecture

The codebase follows a layered architecture:

1. API Layer (`app/api`)

- REST routers and GraphQL router wiring
- Request dependencies and context creation
- Error-to-HTTP translation
- streaming config

2. Service Layer (`app/services`)

- Business workflow orchestration
- Transaction boundaries for writes (`async with <session>.begin()`)

3. Repository Layer (`app/db/*/repos`)

- Postgres repositories for relational data
- Influx repository for telemetry query/write logic

4. Data Model / Schemas

- SQLAlchemy ORM models (`app/db/postgres/orm.py`)
- Pydantic request/response schemas (`app/schemas`)
- Strawberry GraphQL types/inputs (`app/graphql`)

## Request and Data Flow

### REST flow

`router -> dependency injection -> service -> repo -> database`

- Routers are thin and mostly call service methods.
- Services own write transactions.
- Repositories do query/build/update work and avoid commits.

### GraphQL flow

- Root resolvers use request-scoped session factory + dataloaders.
- Nested list fields use Relay connections with keyset pagination.
- Connection batching is implemented in `app/graphql/connection_batching.py`.

### Telemetry flow

`REST/GraphQL telemetry query -> TelemetryService -> TelemetryRepo -> InfluxDB Flux query`

- Telemetry points are written/read from InfluxDB.
- Window reads use `limit`, `has_more`, and `next_end`.
- Stream endpoints are the full-range/export path for telemetry reads.
- Bucket defaults to `INFLUX_BUCKET`, but can be overridden per query.

## Data Model (Relational)

Main entities:

- `Patient`
- `Case` (belongs to patient)
- `Device`
- `Wearable`
- `Context`
- `FHIRMapping`
- `DotDependencyFile` (belongs to mapping)

Association tables:

- `CaseDevice` (temporal assignment: `assigned_from`, `assigned_to`)
- `CaseWearable` (temporal assignment: `assigned_from`, `assigned_to`)
- `CaseContext` (many-to-many)

Important relational constraints:

- Device and wearable temporal overlap prevention via exclusion constraints.
- Check constraints enforcing `assigned_to > assigned_from` when `assigned_to` is set.
- Additional connection/query indexes for keyset and grouped pagination paths.

## Telemetry Model (InfluxDB)

Core telemetry tags include IDs used to link back to relational entities:

- `patient_id`, `case_id`, `device_id`, `wearable_id`, `mapping_id`, `context_id`
- `dot_dependency_file_id`

Each point also includes:

- `measurement`
- `timestamp`
- `fields` (dynamic values)
- `other_tags` (additional tag metadata)

Telemetry read modes:
 
 - Structured reads group field rows into one logical telemetry item. Returned items include `tags` (containing both core and non-core tags) and `fields`. The write payload uses `other_tags` for non-core tags.
 - Raw reads return one row per field value and expose tags as flat top-level keys.
 - Note: `other_tags` is part of the write model (`TelemetryCreate`); structured read responses merge non-core tags into the returned `tags`. See [app/schemas/telemetry.py](app/schemas/telemetry.py#L1-L80) for details.

## Project Structure

```text
app/
  api/              # REST + GraphQL routers, dependencies, error handling
  core/             # settings, domain exceptions
  db/
    postgres/       # SQLAlchemy engine, ORM models, Postgres repos
    influx/         # Influx client + telemetry repo package
  graphql/          # schema, types, resolvers, connections, batching
  schemas/          # Pydantic I/O models
  services/         # business services
  telemetry/        # telemetry shared constants, tag helpers, and types
alembic/            # DB migrations
tests/              # unit, integration, smoke, perf
```

## Local Development

### Prerequisites

- Python 3.14+
- `uv`
- Docker (for Postgres/Influx and integration tests)

### Install dependencies

```bash
uv sync --all-groups
```

### Start dependencies

```bash
docker compose up --build
```

### Run migrations

```bash
uv run alembic upgrade head
```

### Run API locally

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Surface

- REST base routes:
  - `/patients`
  - `/cases`
  - `/devices`
  - `/wearables`
  - `/contexts`
  - `/fhir-mappings`
  - `/telemetry`
  - `/graphql`
- Health:
  - `/livez` (liveness)
  - `/readyz` (dependency readiness)

FastAPI docs are available at `/docs`. 
GraphiQL is enabled when `ENVIRONMENT != "production"`.

## Migrations

Apply latest:

```bash
uv run alembic upgrade head
```

Create migration:

```bash
uv run alembic revision -m "describe_change"
```

Create autogen migration:

```bash
uv run alembic revision --autogenerate -m "describe_change"
```

Notes:

- Autogenerate requires reachable configured Postgres.
- Keep schema changes and migration files aligned.

## Testing

Quick commands:

```bash
# full suite
uv run pytest -q

# unit + smoke only
uv run pytest -m "not integration" -q

# integration only
uv run pytest -m integration -q
```

See `tests/README.md` for detailed fixture/test conventions.

## Configuration

Main settings live in `app/core/config.py` and are loaded from `.env`.

- Postgres connection + pool tuning
- Influx connection + schema cache
- GraphQL safety/performance limits
- Healthcheck timeouts
- Error payload detail mode (`ERRORS_INCLUDE_TECHNICAL_DETAILS`)

## Operational Notes

- DB connection budget warning is emitted at startup based on:
  - `WEB_CONCURRENCY * (DB_POOL_SIZE + DB_MAX_OVERFLOW)`
- GraphQL WebSocket protocol is `graphql-transport-ws`.
- GraphQL GET queries are disabled in production mode.
