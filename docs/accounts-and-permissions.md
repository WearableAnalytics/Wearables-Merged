# Persistent staff accounts and existing access flow

This branch starts from main at `8210a007c57beab5f0717bb9379ff3094b2c3868`.
It keeps the existing staff registration, approval, email-link login and role-based workflows.
It does not require the other foundation branches.

## User flow

1. A person registers an email and requests practitioner or researcher access.
2. PostgreSQL stores a pending account and its requested role. Registration grants no protected access.
3. An administrator approves or denies the registration. Approval applies the requested staff role.
4. An approved person requests an email sign-in link. Only a digest of the random proof is stored.
5. Verification consumes that proof once and creates an expiring, HTTP-only web session.
6. Each protected BFF request checks the current stored account, approval, roles and session version.

Existing users can request another staff role or admin access. The Requests queue remains part of this flow.
Initial registration and additional access requests are separate queue entries; a new registration appears once.
Public responses do not disclose whether an account is registered, pending or denied.
The production email provider is still Brevo. Delivery is not validated against a real mailbox in local tests.

## What changes from main

| Area | Main | This branch |
| --- | --- | --- |
| Staff accounts, roles and approvals | Per-process BFF maps | Shared PostgreSQL records |
| Registration and role requests | Existing UI and flow | Same flow, persisted requested/granted authority |
| Admin actions | Existing controls | Stored revisions, actor/version checks, transactions and audit records |
| Email login proofs | Per-process map | Digest only, expiring, single-use database proof |
| Web sessions | Signed cookie plus current in-memory account | Typed/issuer/audience-bound cookie plus current database authority and revocation version |
| Logout and authority changes | Local cookie/current process state | Earlier account web sessions become invalid across BFF instances |
| Request limits | No shared account admission state | Database-backed client/email limits and bounded HTTP/private-API requests |
| Grafana authorization | Session JWT claims | Current approved practitioner/admin authority through the BFF |

Main already had login, registration, roles, approval and server-side role checks. These concepts are not new.
This branch makes that existing system persistent, shared and revocable.

## Existing roles and workflows

- Practitioners and admins retain the patient overview, case views and Add Case behavior.
- Researchers and admins retain the research/export API and personal token controls.
- Admins retain account/role approval, role changes, denial and unblock controls.
- Practitioner + Researcher retains both staff roles.
- Main's case creation, dashboard embedding, QR UI and extraction proxy paths are retained.

Mandatory staff-to-case assignments, the case-permission screen, public-signup removal,
individual password login, temporary passwords and password resets are not in this branch's final scope.
The earlier local implementation remains in Git history at `5901e0d` for a separate future review.
No new patient/study access policy, mobile capture, consent system or export format is introduced here.

## Stored state and controls

The account migration adds `control_users`, `control_authority_lock`, `control_audit`,
`login_challenges` and `auth_attempts`. It changes no patient, case or measurement rows.
There is no second account database requirement: the tables live in the existing db_lord PostgreSQL service.
No staff authority is kept in a BFF map. `USE_MOCK_DATA` affects clinical demo data, not staff authority.

Account UUIDs, canonical email, approval, granted roles, requested roles, revisions and session versions are persisted.
The email comparison policy remains the existing trimmed/lowercase policy; changing it later needs an identity migration.
Bootstrap is insert-only and restricted by the database's configured admin email allowlist.
A later login/startup cannot restore a denied account or removed admin authority.

Email proofs use 32 random bytes and a SHA-256 digest. They expire within one hour (the demo uses ten minutes).
Reissue invalidates the previous proof. Consumption checks current approval and account version under row locks.
Consumed, expired and stale proofs cannot create another session. Proofs and full login URLs are not logged.
Development does not send email. Production refuses to start without the configured sender, provider key and HTTPS URLs.
Provider delivery failure is logged with a fixed message; this is not a durable email-delivery queue.

Database-backed limits use HMAC subject keys, not raw email/IP strings: 100 client attempts,
10 login attempts per email, five registrations per email, and 30 verification attempts per client per 15-minute window.
Counters are shared across instances, bounded and expired entries are removed in small batches.
`TRUSTED_PROXY_CIDRS` is optional; set only the actual trusted ingress IPs/CIDRs. Untrusted forwarded IP headers are ignored.
Generic response bodies reduce account enumeration; external email-delivery timing is not made constant-time.

Admin UI actions send the displayed target revision. Stale edits are rejected rather than overwriting another change.
The shared authority lock protects concurrent privileged changes and the last active administrator.
Audit rows record account registration, bootstrap, authority changes, login and session revocation.
This is not a complete institutional read-access audit or retention platform.

The session version revokes web sessions. Personal API tokens have separate revocation controls;
their owner must still be currently approved and have researcher/admin authority.
Existing phone/case tokens have a separate lifecycle. Previously delivered or downloaded data cannot be recalled.

## Service boundaries

The database control API requires its private workload credential and checks actor authority on mutations.
Legacy database REST/GraphQL requires `X-Legacy-Operator-Token`. Personal-token storage uses a distinct
`X-Api-Token-Service-Token`. The BFF and extraction client send the appropriate private capability.
Legacy database GraphQL sockets remain closed; they have no continuing staff-session protocol.
Do not expose the database, extraction service or Grafana directly as an alternative public data path.

The Grafana relay checks the current BFF account for HTTP requests and WebSocket upgrades.
Established WebSockets are rechecked every five seconds and closed on lost authority or an outage.
This is the existing broad practitioner/admin policy, not study/case-specific data authorization.
The relay does not dump patient identifiers, cookies or request headers into its debug output.
Configure `AUTH_API_URL` to the trusted BFF `/api/me` endpoint (HTTPS outside loopback development).

Unknown patient DOB remains null through the existing API clients instead of becoming today's date.
This small compatibility correction has no effect on which role can access a patient.

## Setup and rollout

Use the component `.env.example` files. Set fresh, distinct workload/operator secrets.
The BFF's `DATABASE_OPERATOR_TOKEN` must match db_lord's `LEGACY_OPERATOR_TOKEN`;
extraction uses the same capability as `DB_LORD_OPERATOR_TOKEN`.
Set `ADMIN_EMAILS` in the BFF and the permitted initial emails in db_lord's `CONTROL_BOOTSTRAP_ADMIN_EMAILS`.

Run the database API with `--no-access-log` so query parameters do not enter the server access log.

From `services/backend/db_lord`:

```sh
uv sync --frozen --group dev
uv run alembic upgrade head
uv run python -m app.bootstrap_admin --email admin@example.test
```

BFF startup can initialize configured admins through the same insert-only allowlisted service operation.
Normal public registration can never select admin/approved authority.
Production uses verified email login and secure cookies; it requires HTTPS for the browser and database authority.
`ALLOW_DEV_AUTH_BYPASS=true` is accepted only with development and loopback-only URLs.
Never enable it for a deployed service. The local demo uses it explicitly so no mail is sent.

Export/review existing in-memory staff approvals before stopping a live main instance; they cannot be recovered from a database
that never stored them. Import/reapprove them through a trusted operator/admin process. Never infer approval from re-registration.
Back up the database and retire older login issuers before rollout. Downgrade removes account tables, not clinical rows.
The earlier password/case-assignment schema was only used locally and was rolled back before this unpublished migration was narrowed.

## Verification and limits

Backend: `uv run pytest tests/unit tests/smoke tests/integration/test_account_flow_postgres.py`.
BFF: `npm run typecheck` and `npm test`. Grafana proxy: `npx tsc --noEmit` and `npm test`.
Web: `npm run lint` and `npm run build`. Extraction: `uv run pytest tests`.

The integration suite uses disposable PostgreSQL 18 and two real BFF processes. It checks migration preservation/reversal,
concurrent admin safety, one-use proofs, shared limits, registration/approval, stale writes, role-based case creation,
shared sessions, role requests, denial, logout and account persistence after restart.
Its database API lifespan is disabled to isolate account/clinical PostgreSQL behavior from Influx; the separate synthetic local demo
uses the normal readiness path with PostgreSQL and empty Influx. No real email or health data is collected.

This finishes the account-persistence scope, not clinical production acceptance. Institutional authentication strength/MFA/SSO,
patient/study-specific access, deployment networking, backup recovery, audit retention and device/data workflows need separate review.
Grafana and extraction authorization tests do not certify a production Grafana/clinical export deployment.

## Change log — 30 October 2026

1. Extracted the account authority work from main into an independent local branch.
2. Added persistent users, requests, revisions, sessions and audit records.
3. At the agreed scope revision, kept main's registration/approval/email-login flow and existing role-based data workflows.
4. Removed mandatory case assignments and password-only account provisioning from the final feature scope.
5. Added shared login limits, current-authority proxy checks, stale UI revision checks and approval-flow regressions.
6. Kept a stable shared React auth context during development refresh. Retained the shared shadcn dropdown/help controls and corrected pending-role display and unknown DOB handling.
7. Kept main and the preserved foundation checkout unchanged. No push or deployment.
