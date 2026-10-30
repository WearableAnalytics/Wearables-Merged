# Accounts and permissions

This branch is based directly on main at `8210a007c57beab5f0717bb9379ff3094b2c3868`.
It contains one feature area: persistent staff accounts and current access decisions.
It does not depend on the other feature branches.

## Before and after

| Area | Before | This branch |
| --- | --- | --- |
| Accounts and approval | BFF process memory | PostgreSQL users, role requests and approval state |
| Administrator setup | Email configuration could recreate authority | Explicit, insert-only database bootstrap; it never restores denied or removed authority |
| Sessions | Web JWT looked up an in-memory account | Typed JWT with issuer, audience and account version; current stored authority is checked on each request |
| Logout | Browser cookie removal | Stored session version changes; copies of earlier cookies are rejected |
| Email login | One-use tokens in one BFF process | Only token digests are stored; one-use redemption works across BFF instances and restart |
| Case metadata | Broad practitioner/admin lists | Explicit case assignment and current clinical role, including for admins |
| Case permission management | No shared case policy | Admin-managed assignment, purpose, read/export scopes, revision check and recorded change reason |
| Personal API tokens | Unknown owner could remain accepted | Missing or unapproved persistent owner is denied |
| Browser commands | CORS and cookie alone | Exact allowed Origin required for commands; secure cookies and HTTPS browser URLs required in production |

Approval, role and case assignment are separate checks. Registration requests access; it grants none.
The existing account approval UI remains. Its new **Manage case permissions** link opens `/admin/case-access`.

A clinical-reference assignment requires an approved practitioner or admin. A synthetic-research
assignment requires an approved researcher or admin. This branch does not authorize clinical data
for a research purpose. Export requires read permission. Deactivation removes access on subsequent
requests. A case relink does not transfer an old patient's assignment to the new patient.

## Compatibility changes that require review

The old data routes cannot enforce the new assignment policy by accepting a login role alone.
These restrictions are deliberate parts of this access change:

- Web patient/case lists and details use `/control/clinical-cases`, under the current actor and assignment.
  Case reads no longer issue a phone upload token.
- Broad `/api/extraction/*` passthrough returns `410 CASE_SCOPED_EXPORT_REQUIRED`.
- The Grafana proxy returns `410 CASE_SCOPED_DASHBOARD_REQUIRED`; its WebSocket upgrades are closed.
  All dashboard JSON definitions and proxy implementation files remain. There is no replacement chart or data pipeline here.
- The sample hospital lookup and automatic patient match are not exposed as a verified clinical identity workflow.
  Hospital lookup/case creation return `503 HOSPITAL_IDENTITY_REQUIRED`. The Add Case form shows why it is disabled.
  Existing cases can be imported through the trusted operator API and then assigned by an admin.
- Old phone QR verification returns `410 MOBILE_ENROLLMENT_REQUIRED`. No collection grant, consent UI or new mobile adapter is included.
- Legacy db_lord REST/GraphQL tools need `X-Legacy-Operator-Token`. This is a privileged operator capability,
  not an end-user credential. Legacy GraphQL sockets are closed because they lack current-authority continuation.
- The API-token workload uses a separate `X-Api-Token-Service-Token`. The BFF does not receive the operator token.

Deployment must keep direct database, Grafana and extraction services private. This branch does not
reconfigure ingress, a cloud cluster, or other services to establish that network boundary.
Previously downloaded data cannot be recalled by changing a permission.

## Data and service boundaries

The migration adds only `control_authority_lock`, `control_users`, `control_audit`, `case_access`
and `login_challenges`. It changes no existing patient, case, measurement or API-token rows.
Existing staff must register and be approved again; process memory is not a durable migration source.
Existing cases start with no assignment. The account bootstrap allowlist does not infer case access.

`ControlService`, `CaseAccessService` and `ClinicalMetadata` use PostgreSQL directly.
There is no archive/canonical superclass, source catalog, normalizer or ingestion dependency.
Current actor checks use the session version again inside case/account write transactions.
Revision checks prevent a stale form from replacing a newer assignment or user state.
A database lock protects the last active administrator during concurrent changes.
Audit rows record committed authority changes in the same transaction. This is not a complete
institutional audit retention or clinical consent evidence system.

Only login-token hashes are stored. Reissue invalidates the previous login link for that account.
A consumed, expired or old-authority login link cannot issue a new session. No login link is logged.
Logout revokes all sessions at the current account version, not just one browser tab.

Patient date of birth remains null when unknown. The shared Patient definition and its two generated
models carry that value without converting it into a date. A small post-generation fix covers the
existing BFF generator's nullable-date serializer; the generator versions are not upgraded.

## Local configuration

1. Use the existing db_lord PostgreSQL 18 and Influx setup, or equivalent isolated development services.
   Do not point these commands at a live project database.
2. Set four distinct private credentials: `CONTROL_WRITE_TOKEN`, optional `CONTROL_READ_TOKEN`,
   `LEGACY_OPERATOR_TOKEN`, and `API_TOKEN_SERVICE_TOKEN` on db_lord. Configure
   `CONTROL_BOOTSTRAP_ADMIN_EMAILS` explicitly. See its `.env.example`.
3. Apply `uv run alembic upgrade head` from `services/backend/db_lord`.
4. In the BFF `.env`, set `DATABASE_API_URL`, the same control/API-token workload credentials,
   and matching `ADMIN_EMAILS`. Set a fresh `JWT_SECRET` of at least 32 characters.
   Do not give the BFF `LEGACY_OPERATOR_TOKEN`.
5. Start db_lord with `--no-access-log` so query parameters do not enter request logs.
   Its normal startup still checks the existing Influx dependency; this branch does not change that service lifecycle.
6. Start the BFF with `npm ci` then `npm run dev`. Account bootstrap must complete before it listens.
   It has no in-memory authority fallback, even when old sample-data helpers exist in the source tree.
7. Start the web app with its existing `/api` development proxy pointed at that BFF.
   Use Admin account approvals, then Manage case permissions with an existing case UUID and approved staff email.

`ALLOW_DEV_AUTH_BYPASS=false` is the default. Local email delivery is suppressed. For synthetic local
review only, set this flag to true; the BFF then binds to `127.0.0.1`. Production rejects the flag,
insecure cookies, non-HTTPS browser/email-link URLs, and missing email delivery configuration.
No real credentials belong in a committed example or test.

## Verification

From `services/backend/db_lord`:

```sh
uv sync --frozen --group dev
uv run pytest tests/unit tests/smoke
uv run pytest tests/integration/test_accounts_permissions.py
```

The integration tests require Docker and disposable PostgreSQL 18 containers. They do not use
existing Compose data. The connected BFF test also requires `npm ci` in `services/backend/wearables-bff`
and Node. It runs the account APIs with Uvicorn lifespan disabled to isolate this feature from Influx;
it does not claim to test the existing full service lifecycle or the wearable pipeline.

From `services/backend/wearables-bff`: `npm ci`, `npm run typecheck`, `npm test`.
From `services/web`: `npm ci`, `npm run lint`, `npm run build`.

Results for this branch are listed in the change log below. Old foundation CI results are not reused
as proof for this independent branch. No hosted workflow or deployment is added here.

## Excluded work

Raw archive, source contracts, normalization, canonical measurements, snapshots/export redesign,
mobile encryption/retries, HealthKit capture, metric inventory, recovery authority, AI/ML and cloud
changes belong in separate reviews. No existing mobile app, Java mapper, ingest service or dashboard
JSON file is changed by this branch.

This is an independently testable access feature for team review. It is not clinical production
approval. Production identity policy, abuse/rate controls, private service routing, key management,
backup/restore behavior, audit retention and institutional acceptance still need deployment review.

## Change log — 30 October 2026

1. Created an independent local branch from main; no old foundation commits were copied.
2. Added the account/case schema, current actor policy, bounded control requests, migration and denial tests.
3. Connected BFF approval, roles, stored login proof and session revocation; removed memory authority fallback.
4. Added case assignment controls, safe session/data clearing, and explicit notices for blocked broad legacy paths.
5. Verified migration/reversal, concurrent admin and login changes, actual BFF/SQL restart and revocation,
   nullable Patient JSON conversion, web lint/build, and scope boundaries.

Validation for this extracted branch: **132 backend unit/startup tests + 3 PostgreSQL integration
tests + 7 Node tests = 142 passing tests**. The changed Python access modules pass Ruff and Pyright;
BFF and Grafana TypeScript checks pass; web lint and build pass. Four browser checks cover the actual
React form and scoped views, including a saved permission revision. Four live HTTP/WebSocket checks
confirm the legacy guards. A fresh synthetic local demo also passed normal database API readiness.
No hosted CI result or clinical production approval is claimed.
