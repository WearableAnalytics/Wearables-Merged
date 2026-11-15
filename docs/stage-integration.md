# Shared stage integration

Target branch: `stage/ws2627`. Initial base: `3f3ca487`.
This combines the current application foundation for team integration. It does
not deploy a staging environment or change the production Argo CD revision.

## Included work

| Feature branch | Integrated head | Scope |
| --- | --- | --- |
| accounts-and-permissions | a02a1b6 | Persistent accounts, current authority, single-use proofs and session revocation |
| reliable-ingestion | 883627c | Retained encrypted uploads, receipts, immutable identities, lineage and controlled recovery |
| ingestion-deployment | 88d3751 | Runtime/migration wiring, latest/Always, explicit internal HTTP and temporary operator login delivery |
| ingestion-source-contract | b5297e9 | Native source metadata and fractional duration compatibility |
| measurement-mapping | a372662 | Numeric meaning, units, periods, validation and synchronized mappings |
| source-reconciliation | 7272a1e | Native provenance, separate/select/priority policies and source-aware views/exports |

All six heads remain in the integration history. The feature branches are not
rewritten or deleted. Other members' unmerged feature branches are not included.

## Merge decisions and compatibility fixes

- Keep stage's Grafana admin ForwardAuth route and verify it against current
  stored authority. Anonymous, non-admin, denied, revoked and unavailable states
  are rejected. Keep recent mobile/cloud code and all eight service image builds.
- Keep the receipt-backed importer and its bounded numeric/source model. Do not
  restore the old asynchronous success response while merging source fields.
- Run numeric normalization before FHIR mapping, retaining participant fallback
  for historical input. Keep both JUnit generations and one shade configuration.
  Synchronize all four mapping copies from the combined canonical YAML.
- Wire the Grafana chart's `session.authApiUrl` to the existing internal BFF
  `/api/me` service. Explicit private HTTP flags preserve the current cluster
  setup without an internal CA. Only Kubernetes service DNS is accepted by
  the production HTTP exception. This traffic remains unencrypted; operators
  must keep it in a trusted cluster network. Current authority is still required.
- Retain operator login links while Brevo is disabled through an explicit chart
  flag. Proofs remain approved-account-only, hash-stored and single-use, with a
  five-minute maximum lifetime. Log readers can use unused links; restrict log
  access. A configured Brevo key turns off log delivery. This is temporary
  operator delivery, not verified email ownership or the development bypass.
- Accept Garmin's existing respiratory-rate and HRV unit spellings without
  scaling their values. Preserve canonical output and the original unit metadata.
- Bind the BFF/proxy explicitly inside local containers. Host development still
  defaults to loopback; the email shortcut cannot bind a network interface.
- Local Compose now receives private account/ingestion credentials, creates
  separate migration/runtime database roles, migrates before startup and waits
  for account readiness. The setup retains existing archive keys. Local sign-in
  uses an approved account's one-use proof, not a service-log token or password.
  See [local setup](../deploy/local/README.md).
- Local Docker HTTP proxy authority uses explicit development mode. Production
  uses the restricted service-DNS exception above. Compose publishes only on
  host loopback. Secure browser cookies and authority checks remain required.

- Patient dashboards now execute their raw InfluxQL queries, including the
  participant alias and source filters/grouping. A separate check runs the
  actual Helm Starlark processor and dashboard queries against isolated InfluxDB,
  covering shared uploaders, separate patients/sources and legacy points.
  The isolated processor runs as the test-file owner for Linux filesystem access.

## Verification on 15 November 2026

- Flutter 3.47.9 with the committed lockfile: 42 tests passed.
- BFF: typecheck and 26 tests passed, including current-authority ForwardAuth,
  disabled email and the loopback-only shortcut guard.
- Grafana proxy: typecheck and nine tests passed, including WebSocket revocation.
- Database: 127 unit/startup/real PostgreSQL checks passed. The real account flow
  uses two BFF processes and covers persistence, approval, revocation and restart.
- Exports/source policies: 70 tests passed. Provider contracts: seven passed.
- Mapper: 23 Java tests and packaging passed. Web production build passed.
- Ingestion contracts, migrations and real Kafka/Java/Telegraf/InfluxDB checks
  passed. The connected test retains native IDs and fractional sleep intervals.
- Two Grafana query/identity tests passed with rendered Telegraf and real InfluxDB.
- All eight application images built locally. The complete core Compose stack
  started with its setup/migration jobs and synthetic data only.
- The running-stack smoke check verified UI delivery, approved sign-in, case
  creation, archive hash/receipt, repeated and conflicting uploads, two sources,
  numeric-looking native IDs, precise FHIR periods, JSON/CSV/FHIR export,
  researcher/admin extraction protection, Grafana authority, staff approval/
  revocation and logout. No real email or wearable data was used.

## CI and promotion boundary

`Stage foundation checks` covers accounts, applications, mobile and the real
ingestion pipeline. The existing image workflow retains cloud/mapper/Grafana
builds and the deployment regression job. Chart lint also runs for stage.

Stage pushes and PRs build/scan images without registry login or publication.
The production deployment job requires the main ref, including manual runs.
Argo CD's checked-in production revision remains `main`. Only the verified
integration is promoted to stage; main and production are not promoted here.

The cluster-side prerequisites from [the deployment guide](ingestion-deployment.md)
still apply: operator-managed credentials, private service account authority,
configured Grafana authority, database/Kafka permissions, matching images/mapping
and coordinated migrations/auto-sync. Local Compose is a synthetic development
profile, not a production deployment. Its default Influx observation credential
can use the local admin token; supply a separate read token for least privilege.

Physical Android/provider validation, clinical terminology/source-policy approval,
institutional authentication requirements and other members' features remain
separate. Stage integration is not clinical production acceptance.
