# Accounts and permissions

This branch starts directly from main at `8210a007c57beab5f0717bb9379ff3094b2c3868`.
Its scope is named staff accounts, password authentication and current case permissions.
It does not depend on the other foundation feature branches.

## Current user flow

1. A trusted operator initializes the first named administrator through the server command.
   The web app cannot bootstrap an administrator or create a default password.
2. An administrator creates a staff account with an email, access profile and temporary password.
   New accounts are approved by this explicit admin action. They receive no case assignment automatically.
3. The administrator gives the temporary password to that person through an approved channel.
   The app sends no invitation or login email. Temporary passwords expire after 24 hours.
4. The person signs in with the temporary password and chooses their own password.
   The temporary login permits only setup, not case data or admin actions. This is enforced in the BFF and database authority.
5. The person can then use the application according to their current role and explicit case assignments.

Public registration is closed. `/api/register` returns `410 SELF_REGISTRATION_DISABLED`.
The old `/register` page redirects to sign-in. Email-link login endpoints return `410 EMAIL_LOGIN_DISABLED`.
`ALLOW_DEV_AUTH_BYPASS=true` is rejected, including in development. No email-only fallback remains.
MFA and SSO are not implemented in this step.

## Who has which authority?

| Access profile | Account management | Case data |
| --- | --- | --- |
| Admin | Create named accounts, assign roles, disable access, reset other accounts and manage case assignments | Requires an explicit eligible case assignment; no automatic global patient access |
| Practitioner | Own profile, theme and password | Clinical-reference case metadata only for assigned cases |
| Researcher | Own profile and password; existing personal API-token management | Research-purpose assignments can be recorded; clinical identity views are denied and the broad export route is blocked |
| Practitioner + Researcher | The combined staff roles; no global account creation | Each request still needs an eligible purpose and case permission |

Several people can have named administrator accounts. One person need not handle every administrative task.
A practitioner does not need an administrator to approve each page view: the server checks their stored assignment.
We have not added a study coordinator or delegated account-manager role. Add a limited, explicitly scoped capability
when the team agrees its study/organization boundary; do not grant all staff global user-management authority.

Approval, role, completed password setup and case assignment are separate checks. Export scope requires read scope.
Deactivation denies later requests. Relinking a case to another patient does not transfer the old patient's assignment.
A case belongs to one patient; a patient can have several cases. Existing `Context` grouping is not a study-level access policy.
This branch adds no clinical notes, study-management UI or clinical case-creation workflow.

## What changed from main

| Area | Before | This branch |
| --- | --- | --- |
| Staff accounts and roles | BFF process memory and public registration | PostgreSQL authority; admin-only account creation |
| Authentication | Email links and development email-only login | Individual passwords; no invitation email or dev bypass |
| Password setup | Not present | Expiring setup password and restricted setup session; personal password required before normal access |
| Sessions | JWT plus in-memory account lookup | Typed password-session JWT, issuer/audience, stored account version and current policy checks |
| Password change/reset | Not present | Own change, admin reset and protected operator recovery; earlier web/setup sessions become invalid |
| Patient/case lists | Broad practitioner/admin visibility | Explicit current clinical case assignment, including for admins |
| Case assignment controls | No shared case policy | Admin UI with purpose, read/export scopes, change reason and revision checks |
| Unknown patient DOB | Could be replaced by an invented date | Null remains null through the shared Patient schema and both generated clients |

## Authentication and storage

`control_users`, `case_access`, `control_audit` and `control_passwords` are in PostgreSQL.
The new credential migration removes the earlier login-challenge table and invalidates previous account-session versions.
It changes no patient, case or measurement rows and infers no password for an existing account.
Existing accounts without a credential require protected administrator initialization or an admin password reset.
A downgrade does not restore old email links or session authority.

Passwords use Argon2id through `argon2-cffi`, with a random salt, 64 MiB memory, three iterations and one lane.
No plaintext password or hash is returned in account responses. Passwords are not put in JWTs, URLs, audit rows or request logs.
New passwords have 15–256 characters, at most 1,024 UTF-8 bytes, with NFC normalization and significant whitespace.
The bundled common-password blocklist is a small local baseline, not a complete compromised-password corpus.
Institution-approved password screening remains part of production identity-policy review.

Each API worker admits at most two password-hashing operations at once, off its event loop. Further work receives `503`.
Failed attempts are stored per account: five failed password attempts lock password verification for 15 minutes.
Resetting a password clears that counter. Unknown, wrong, expired and inactive credentials do not authenticate.
Deployment still needs appropriate network-level abuse controls and a memory budget for every worker.

Temporary setup sessions last at most ten minutes and use a distinct JWT audience/type. They cannot authenticate ordinary APIs.
Credential changes increment the stored account version. Case/admin commands check current authority again inside transactions.
A privileged-write lock protects the last usable administrator; an admin awaiting password setup does not replace that safeguard.
Staff forms use expected revisions to prevent stale updates. Audit entries commit with the authority change.
The audit table is not a complete institutional audit-retention or consent-evidence system.

Normal web sessions use HTTP-only cookies, exact command-Origin checks and bounded JSON inputs.
Production requires secure cookies, HTTPS browser URLs and HTTPS to the password-authority API.
Password validation errors are fixed messages, including when the API is behind a path prefix.
A database outage does not enable memory authority or email-only access.

## UI

- `/login`: email and individual password; no registration action.
- `/set-password`: restricted first-login/reset setup. The current temporary password and a different personal password are required.
- `/admin/approvals`: existing account-management layout plus Create staff account and Reset password controls.
- `/admin/case-access`: select an existing case and approved staff member, then set purpose, scopes and a recorded reason.
- `/overview`: Assigned cases; only the current permitted clinical cases appear.
- `/account`: access summary, theme and own password change. Role/access changes go through an administrator.

An admin cannot reset their own password through the staff reset action. They use their current password in Account.
If the password is lost, another named admin can reset it, or a trusted server operator can use the recovery command below.
Recovery changes credentials only; it does not reactivate a denied account or restore removed admin authority.
Already delivered/downloaded data cannot be recalled by a later permission change.
Personal API tokens have their own revocation controls; the broad extraction route does not accept them for data export in this branch.

## Deliberate compatibility limits

These paths cannot safely apply case assignments through their former broad interfaces:

- `/api/extraction/*` returns `410 CASE_SCOPED_EXPORT_REQUIRED`.
- The Grafana proxy returns `410 CASE_SCOPED_DASHBOARD_REQUIRED` and closes WebSocket upgrades.
  Dashboard JSON definitions and proxy files remain; no replacement chart or data pipeline is added.
- Sample hospital lookup and automatic patient matching return `503 HOSPITAL_IDENTITY_REQUIRED`.
  The Add Case form states why it is disabled. Use trusted operator import and explicit staff assignment for existing cases.
- Old phone QR verification returns `410 MOBILE_ENROLLMENT_REQUIRED`. Mobile enrollment and collection consent are separate features.
- Legacy db_lord REST/GraphQL tools require `X-Legacy-Operator-Token`. The BFF does not receive this privileged operator capability.
  Legacy GraphQL sockets are closed. The existing API-token workload has a distinct credential.

Keep direct database, Grafana and extraction services private. No cloud, ingress, cluster or main-branch change is included.

## Local setup and administrator recovery

Use an isolated development database, not a live project database.
The existing db_lord normal lifecycle still checks PostgreSQL 18 and Influx; this feature does not change that lifecycle.
Set distinct workload/operator credentials as described in the component `.env.example` files.
Configure `CONTROL_BOOTSTRAP_ADMIN_EMAILS` on the database service for the named initial/recovery administrator.

From `services/backend/db_lord`:

```sh
uv sync --frozen --group dev
uv run alembic upgrade head
uv run python -m app.bootstrap_admin --email admin@example.test
```

The server command prompts for a password twice; never supply one as a shell argument.
It initializes only a permitted, active admin identity without an existing credential. It does not overwrite authority or a password.
For protected operator recovery of an existing active administrator:

```sh
uv run python -m app.bootstrap_admin --email admin@example.test --reset-password
```

Recovery prompts for a reason and a new temporary password, invalidates older web sessions, and requires personal password setup.
Treat server/DB access to this command as privileged. There is no corresponding HTTP bootstrap/recovery endpoint.

Start db_lord with `--no-access-log`, then the BFF and web using their existing development commands and correct proxy URLs.
The BFF always uses database authority. `USE_MOCK_DATA` does not provide in-memory accounts or permissions.
Configure and migrate the database before starting the updated application; retire old login issuers during deployment.
No default password or private local-demo credential is committed.

## Verification and review boundary

From db_lord: `uv run pytest tests/unit tests/smoke` and `uv run pytest tests/integration/test_accounts_permissions.py`.
The integration test uses disposable PostgreSQL containers, not existing Compose volumes. It also needs Node and BFF `npm ci`.
Its connected BFF/account test disables the database app lifespan to isolate PostgreSQL authority from Influx;
a separate synthetic demo checks the normal database readiness path.
From the BFF: `npm run typecheck` and `npm test`. From web: `npm run lint` and `npm run build`.

Current local verification: **145 backend unit/startup tests + 3 PostgreSQL integration tests + 9 Node tests = 157 passing tests**.
Nine browser checks cover actual account creation, case assignment, restricted first login, personal password setup,
practitioner denial, admin reset, old-password rejection and repeated setup after reset.
Changed Python modules pass Ruff/Pyright. BFF TypeScript, web lint/build and the local Linux backend image build pass.
No hosted CI run or clinical production approval is claimed.

Raw archive, normalization, canonical measurements, export redesign, mobile delivery/capture, metric inventory,
data replay/recovery, AI/ML, study-level delegation and cloud work remain separate.
MFA/SSO, institutional identity policy, abuse controls, secret management, backup/restore and audit retention require production review.

## Change log — 30 October 2026

1. Created the independent branch from main and extracted persistent account/case authority without the large foundation history.
2. Added explicit case assignments, protected metadata, current-session checks and the account/case UI.
3. Closed public signup and email authentication; added admin-created named accounts, password setup/change/reset and server recovery.
4. Added credential migration, password hashing/throttling, temporary-session restrictions and regression/real-browser checks.
5. Kept the work local. Main and the preserved foundation branch are unchanged; no push or deployment was performed.
