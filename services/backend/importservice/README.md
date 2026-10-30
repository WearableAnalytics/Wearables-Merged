# Wearables Import Service

Accept numeric wearable batches into an encrypted PostgreSQL upload archive and
publish them through the existing Kafka/FHIR/Telegraf/InfluxDB pipeline.

See [reliable ingestion](../../../docs/reliable-ingestion.md) for the contract,
architecture, migration, runtime settings, recovery, verification and limits.

- `POST /ingest`: 202 after atomic archive commit; a receipt does not mean that
  processing or InfluxDB delivery is complete.
- `GET /ingest/{acceptanceId}`: scoped progress and storage observations.
- `POST /ingest/{acceptanceId}/retry`: bounded retry of failed work.
- `/health`: process health; `/ready`: archive readiness; `/docs`: API schema.

Run `python -m app.migrate` with migration credentials before starting the service.
The runtime role needs only the documented schema privileges. There is no default
JWT secret or in-memory archive fallback. Provision keys and credentials outside
Git. Ordinary runtime must not own the archive tables.

For local checks, install `requirements.txt` plus pytest, pytest-asyncio and Ruff.
Run `ruff check app tests` and `pytest -q` from this directory. The dedicated
PostgreSQL and connected-stack tests are described in the linked document.
