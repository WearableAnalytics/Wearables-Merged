# Shared stage integration

Target branch: `stage/ws2627`. Initial base: `3f3ca487`.
This combines the current application foundation for team integration. It does
not deploy a staging environment or change the production Argo CD revision.

## Included work

| Feature branch | Integrated head | Scope |
| --- | --- | --- |
| accounts-and-permissions | a02a1b6 | Persistent accounts, current authority, single-use proofs and session revocation |
| reliable-ingestion | 883627c | Retained encrypted uploads, receipts, immutable identities, lineage and controlled recovery |
| ingestion-deployment | b262fc2 | Runtime/migration wiring and Carl's latest/Always/disabled-email compatibility review |
| ingestion-source-contract | b5297e9 | Native source metadata and fractional duration compatibility |
| measurement-mapping | 50b5088 | Numeric meaning, units, periods, validation and synchronized mappings |
| source-reconciliation | 9bece23 | Native provenance, separate/select/priority policies and source-aware views/exports |

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
- Configure the Grafana chart's `session.authApiUrl` as its trusted HTTPS BFF
  `/api/me` endpoint before cutover. Empty configuration denies protected proxy
  requests. There is no fallback to stale account claims in a JWT.
- Bind the BFF/proxy explicitly inside local containers. Host development still
  defaults to loopback; the email shortcut cannot bind a network interface.
- Local Compose now receives private account/ingestion credentials, creates
  separate migration/runtime database roles, migrates before startup and waits
  for account readiness. The setup retains existing archive keys. Local sign-in
  uses an approved account's one-use proof, not a service-log token or password.
  See [local setup](../deploy/local/README.md).
- Private HTTP proxy authority is allowed only with explicit development mode.
  Compose publishes ports only on host loopback. Production authority, cookie
  and authentication requirements remain in force.

## Verification on 15 November 2026

- Flutter 3.47.9 with the committed lockfile: 42 tests passed.
- BFF: typecheck and 23 tests passed, including current-authority ForwardAuth,
  disabled email and the loopback-only shortcut guard.
- Grafana proxy: typecheck and eight tests passed, including WebSocket revocation.
- Database: 127 unit/startup/real PostgreSQL checks passed. The real account flow
  uses two BFF processes and covers persistence, approval, revocation and restart.
- Exports/source policies: 70 tests passed. Provider contracts: seven passed.
- Mapper: 22 Java tests and packaging passed. Web production build passed.
- Ingestion contracts, migrations and real Kafka/Java/Telegraf/InfluxDB checks
  passed. The connected test retains native IDs and fractional sleep intervals.
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
still apply: operator-managed credentials, private HTTPS account authority,
configured Grafana authority, database/Kafka permissions, matching images/mapping
and coordinated migrations/auto-sync. Local Compose is a synthetic development
profile, not a production deployment. Its default Influx observation credential
can use the local admin token; supply a separate read token for least privilege.

Physical Android/provider validation, clinical terminology/source-policy approval,
institutional authentication requirements and other members' features remain
separate. Stage integration is not clinical production acceptance.
