# Wearables BFF — accounts and permissions

Read the [complete scope, authority model, setup and limits](../../../docs/accounts-and-permissions.md).
This branch uses PostgreSQL-backed staff authority through db_lord. There is no in-memory account fallback.

## Sign-in and provisioning

Staff sign in with an individual email and password. Only an authenticated, current administrator can create staff accounts.
A newly issued/reset temporary password expires after 24 hours and permits password setup only.
Users must choose their own password before accessing normal application or admin APIs.
No public registration, invitation email, magic-link login or email-only development bypass is available.
MFA and institutional SSO are outside this step.

Initialize the first named administrator with the protected db_lord server command. This BFF never creates an administrator at startup.
`ALLOW_DEV_AUTH_BYPASS=true` is an invalid configuration. Existing web sessions from the prior authentication method are invalidated.

## Main routes under API_PREFIX

| Route | Access and behavior |
| --- | --- |
| `POST /login` | Email/password verification; normal session or restricted password-setup session |
| `POST /password/setup` | Restricted setup cookie plus temporary password and new personal password |
| `GET /me` | Current authenticated account |
| `POST /account/password` | Own current password and a different new password; old web sessions invalidated |
| `POST /logout` | Revokes the current stored web-session version and clears login/setup cookies |
| `POST /admin/users` | Current admin; named staff identity, role and temporary password |
| `POST /admin/users/:id/password-reset` | Current admin; expected account revision; other approved accounts only |
| Existing `/admin/*` review/update routes | Current admin; persisted roles/status and last-usable-admin guard |
| `/admin/case-access/:caseId/:userId` | Current admin; explicit case assignment and revision checks |
| `/patients`, `/cases` and their detail routes | Current clinical authority and explicit case assignment |
| `POST /register`, `GET /verify-magiclink` | Closed: 410 |
| `/extraction/*` | Broad data passthrough blocked: 410 pending a separate case-scoped export feature |

Passwords are forwarded only to the private password authority; production requires HTTPS for that connection.
The BFF stores no password/hash. Sessions use typed signed cookies and current account versions; role claims from clients do not grant authority.
Every browser command requires an exact configured Origin. Inputs, replies and in-flight requests are bounded.
The BFF never receives the legacy operator credential.

## Run locally

1. Configure and migrate db_lord, then initialize a named administrator.
2. Copy `.env.example` to your private `.env`; set fresh distinct secrets and exact development URLs.
3. Run `npm ci` and `npm run dev`.
4. Point the web development `/api` proxy at this BFF.

Development binds to `127.0.0.1`. There are no automatic sample users or default passwords.
Startup checks database authority availability. It does not infer or restore account privileges from environment email lists.

## Checks

```sh
npm ci
npm run typecheck
npm test
```

The db_lord PostgreSQL integration test also exercises actual BFF creation, password setup/change/reset,
case access, process restart, revocation and logout. See the shared scope document for results and remaining deployment review.
