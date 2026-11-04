# Reliable-ingestion deployment

Branch: `ingestion-deployment`. Parent: `reliable-ingestion` at `883627c`.
Review this branch against that parent. This implements the deployment work in
[#113](https://github.com/WearableAnalytics/Wearables-Merged/issues/113).
It does not change clinical metrics, mobile collection or the account workflow.

## Changes

- Importer: configure PostgreSQL, archive/signing keys, results delivery, request
  limits and InfluxDB storage observation through ConfigMap and Secret references.
  Readiness uses `/ready`; liveness remains `/health`. Readiness checks the
  permissions needed to accept and process uploads, including archive protection.
- Migration: a pre-install/pre-upgrade Job runs the same importer image with a
  separate database credential. A transaction and advisory lock serialize schema
  setup and runtime grants. A migration ledger detects changed applied SQL.
  An older image refuses newer migration history; Windows line endings do not
  change a migration checksum.
  Repeated runs preserve accepted data. An installation made with the original
  direct `001_ingestion.sql` is adopted only when its table, column, constraint
  and index definitions match a baseline created temporarily on the same server.
  A partial or different legacy schema is rejected without altering its data.
- Runtime grants: schema usage; SELECT/INSERT on uploads and upload links;
  SELECT/INSERT/UPDATE on records and outbox; INSERT on events and sequence usage.
  The runtime cannot update/delete the raw archive, create schema objects, or
  change migration history. The role must already exist as an unprivileged login
  and must not inherit the migration/schema-owner authority.
  Retry handling locks the mutable record rows instead of the immutable upload;
  concurrent retries cannot advance one rejected generation twice.
- Mapper: receive only the shared ingestion signing key, plus optional Kafka
  transport credentials. Configure the results topic. Roll the Pod when its
  environment or mounted mapping changes. The deployed mapping now preserves
  collector identity as `source-device-id` and uses `participantId` for the patient.
  The FHIR export default has the same identity fields; a rendered contract check
  compares all four committed YAML copies. Existing database-supplied custom
  mappings and metric/unit semantics remain part of mapping review #115.
- Kafka: provision `wearables-ingestion-results`, with 30 partitions, three
  replicas and seven-day retention in the existing Kafka chart. Operators must
  retain their cluster-specific capacity, durability, TLS and ACL settings.
- Images: build/test/publish the mapper through the existing image workflow.
  Build and runtime use Java 17; `JAVA_TOOL_OPTIONS` controls its heap with the
  existing 3500 MiB default. Both service charts require an explicit image tag or
  digest, rather than silently selecting the old mapper or a floating default.
- Verification: add rendered Helm contract checks and real PostgreSQL migration,
  recovery and permission tests. PostgreSQL-backed regression and connected
  pipeline tests now use an unprivileged runtime login.

## Required operator inputs

Provision these existing Secrets outside Git before installing the chart.
Names and key names can be overridden in chart values. Values below are key
names, not credentials.

| Namespace/workload | Default Secret | Required keys |
| --- | --- | --- |
| Importer | `importservice-secrets` | `JWT_SECRET`, matching the BFF issuer/key |
| Importer | `importservice-ingestion` | `INGEST_DATABASE_URL`, `INGEST_ARCHIVE_KEY`, `INFLUXDB_TOKEN`; optional `INGEST_ARCHIVE_OLD_KEYS` |
| Importer migration Job only | `importservice-migration` | `INGEST_DATABASE_URL` for the migration authority |
| Importer and mapper, in each release namespace | `ingestion-signing` | `INGEST_SIGNING_KEY`, with the same value in both namespaces |

The archive and signing keys must be distinct base64-encoded 32-byte keys.
Only the importer receives the archive key. `INFLUXDB_TOKEN` must have READ
permission on the configured bucket; Telegraf retains its separate write token.
Each journal database needs a distinct `KAFKA_RESULTS_GROUP`; replicas of one
journal share that group. Set `INFLUXDB_URL`, organization and bucket for the
actual installation.

Use the existing PostgreSQL instance or a dedicated database. An operator first
creates the unprivileged LOGIN role named by `migration.runtimeRole` (default
`wearables_ingest`) and its credential. The migration role needs authority to
create/own the ingestion schema and grant its privileges; baseline adoption also
requires database CREATE permission for the temporary validation schema. The
runtime and migration DSNs must reach the same database. Their Secret names must
differ. Use TLS with certificate verification for remote PostgreSQL connections.

For Kafka TLS/SASL, set `kafkaSecuritySecret.name` on each service. The importer
expects `KAFKA_SECURITY_JSON`; the mapper expects
`KAFKA_SECURITY_PROPERTIES_JSON`. These are the existing client-specific formats,
not interchangeable JSON documents. Certificate Secrets can be mounted using
`extraVolumes` and `extraVolumeMounts`. Migration-only database certificate
mounts use `migration.extraVolumes` and `migration.extraVolumeMounts`.

The hook does not create Kubernetes Secrets or database login passwords. It
contains no archive, JWT, signing or InfluxDB credential references. Keep
migration authority unavailable to the normal importer Pod.

## Release order and mobile compatibility

1. Review the parent account and reliable-ingestion changes. Provision the
   database roles, database/TLS access, matching signing Secrets, archive keys,
   bucket read token and Kafka topic/ACL configuration.
2. Integrate the intended mapper binary and mapping changes into one release.
   [#114](https://github.com/WearableAnalytics/Wearables-Merged/pull/114) adds
   `normalizeTimestamp`; use its updated binary and all matching YAML changes
   together. Do not mount that transformation into an older mapper. Carl's
   [#112](https://github.com/WearableAnalytics/Wearables-Merged/pull/112) currently
   includes that mobile work. This branch does not duplicate their mobile commits.
3. Build the release images through `Publish service images`. Choose the
   published commit SHA tag or image digest explicitly in both charts. Render
   the charts from the same release source. PR checks build images without
   publishing them; the workflow publishes only on `main` or an explicit run.
4. Complete the schema/grant Job before the receipt-backed pipeline is enabled.
   The Helm importer hook blocks its install/upgrade until the Job succeeds.
   For the first cross-service cutover, run that Job as a separate controlled
   step, then roll the mapper, then the importer. With separate GitOps releases,
   enforce this order in the operator's release orchestration. A chart does not
   order separate releases automatically.
5. Verify a synthetic upload: real HTTP 202, matching body hash/count, receipt
   lookup, broker/result milestones, and `storage-observed` from InfluxDB. Then
   release the updated mobile app. A client-generated receipt or legacy HTTP 200
   does not prove server-side archival.

For rendering only, substitute a built release tag:

```sh
helm template importservice gitops/apps/services/importservice --namespace importservice --set image.tag=RELEASE_SHA
helm template mapper-validator gitops/apps/services/mapper-validator --namespace kafka --set image.tag=RELEASE_SHA
```

These commands do not deploy. Secret changes used as environment variables need
a controlled Pod restart. Signing-key rotation requires a coordinated drain and
cutover; dual-key verification is not implemented. Retain old archive keys when
rotating the current archive key. Never roll back to the unacknowledged importer
while presenting its responses as archived receipts. Migration Jobs have no down
migration or data-deletion action. Archive retention policy remains separate work.

## Local checks and change log

Use `HELM_BINARY` if Helm is not on PATH. From `services/backend/importservice`:

```sh
ruff check app tests
pytest -q --ignore=tests/test_connected.py --ignore=tests/test_deployment_connected.py
```

PostgreSQL checks require `INGEST_TEST_DATABASE_URL` and refuse any database
other than the disposable `ingestion_test` database. They create temporary login
roles and reset only that test schema; never point them at a real archive.
`tests/compose.yaml` provides the isolated synthetic stack described in
[reliable-ingestion.md](reliable-ingestion.md). Package the mapper before the
connected test. `INGEST_TEST_MAPPER_CONFIG` can select the rendered Helm mapping
so that the connected run verifies the configuration actually deployed.

The built-image check requires the disposable compose project named
`ingestion-deployment-test`, its default network, and locally built images named
`wearables-ingestion-deployment-importer:local` and
`wearables-ingestion-deployment-mapper:local`. Set `INGEST_TEST_IMAGES=1`,
`INGEST_TEST_LOG_DIR` to a private directory, and the test database/InfluxDB
settings from that stack, then run `pytest -q tests/test_deployment_connected.py`.
It refuses a remote Docker engine. It runs the migration command twice, uses a
bucket-read-only observation token, checks a real 202 receipt and repeat/conflict
behavior, pauses only this test stack's Kafka, and verifies eventual storage after
resuming it. Temporary credential files and test app containers are removed.

Completed implementation steps on 2026-11-04:

1. Checked current GitHub changes and #113–#118; kept the task on deployment #113.
2. Added Secret-based runtime wiring, migration lifecycle and least-privilege
   grants; added upgrade/adoption/rollback and readiness regression checks.
3. Aligned Helm identity mapping, results topic, mapper configuration rollout and
   image build/publication. Added CI checks using PostgreSQL and rendered charts.

Local validation completed on 2026-11-04:

- 66 importer/deployment regression checks passed, including ten real PostgreSQL
  migration/permission checks and ten rendered Helm contract checks.
- 12 Java tests and mapper packaging passed; 18 extraction/export tests passed.
- Both service images built. The connected pipeline check passed using the
  rendered Helm mapping and unprivileged PostgreSQL runtime role. A separate
  built-image check passed, including repeat migration, real HTTP receipts,
  conflict rejection, Kafka outage acceptance and observed storage after recovery.
- Ruff, Helm lint, workflow actionlint and Git whitespace checks passed.
- A temporary combination with the current mobile branch at `2df79e0` had no
  Git conflicts. Its backend checks passed: 66 importer/deployment, 15 Java,
  44 extraction/export, and a connected run with `normalizeTimestamp` and the
  combined rendered mapping. This was a local compatibility snapshot, not a merge.

The current mobile branch has a separate test-compilation problem:
`UploadReceipt.readingCount` and `UploadReceipt.rawSha256` are referenced by its
tests but are not defined. It also accepts legacy HTTP 200 by creating a synthetic
archived receipt. That fallback is not evidence of a retained backend upload.
Those mobile changes need separate review before mobile release; this branch
changes no mobile implementation. One existing Starlette/AnyIO deprecation
warning remains in importer tests. These checks do not replace a physical-device
test, Kubernetes rollout verification, load testing or operator approval.

No production deployment is part of this branch. Operator secrets, TLS/ACL
settings and the clinical mapping work in #115–#118 remain separate inputs/work.
