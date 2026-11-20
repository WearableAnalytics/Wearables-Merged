# Wearables BFF

This branch keeps the existing registration, admin approval, email-link login and practitioner/researcher/admin workflows.
Staff authority is stored in db_lord PostgreSQL, including requests, revisions, login proofs and session revocation versions.
`USE_MOCK_DATA` changes clinical data only; it never enables in-memory staff accounts.

See [the branch guide](../../../docs/accounts-and-permissions.md) for the exact changes, setup, limits and verification.

```sh
npm ci
# Configure the variables from .env.example and migrate db_lord first.
npm run dev
```

The BFF needs distinct `CONTROL_WRITE_TOKEN`, `API_TOKEN_SERVICE_TOKEN`, `DATABASE_OPERATOR_TOKEN` and a private `JWT_SECRET`.
`DATABASE_OPERATOR_TOKEN` matches db_lord's `LEGACY_OPERATOR_TOKEN`. Production uses HTTPS browser/database URLs and secure cookies.
`BREVO_API_KEY` may be absent or `disabled` during rollout. The BFF starts, but new email-login requests return 503 before any account lookup or proof creation.
The response is the same for all valid email addresses. Existing sessions and already-issued links still require normal stored-authority checks.
No login link, proof or recipient is logged as a fallback. A real provider key and configured sender enable normal email delivery after a controlled restart.
The development email shortcut must be explicitly enabled and is limited to loopback URLs. Development sends no email.

Public registration creates a pending record, never admin/approved access. With email available, `/api/login` gives a generic response unless the explicit local shortcut is active.
Email proofs are one-use database records. Protected routes use current stored roles and approval; admin changes include the displayed record revision.

The existing case, enrollment and extraction paths remain. Fine-grained case/study policy is separate work.
Keep extraction, database and Grafana backends private. Grafana should use this BFF's `/api/me` for current session authority.

Verification: `npm run typecheck`, `npm test`, and the real PostgreSQL/BFF integration test listed in the branch guide.
