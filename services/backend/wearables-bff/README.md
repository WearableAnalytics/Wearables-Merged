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
`DATABASE_OPERATOR_TOKEN` matches db_lord's `LEGACY_OPERATOR_TOKEN`. Production uses HTTPS browser/database URLs and a configured email sender/provider.
The development email shortcut must be explicitly enabled and is limited to loopback URLs. Development sends no email.

Public registration creates a pending record, never admin/approved access. `/api/login` gives a generic response unless the explicit local shortcut is active.
Email proofs are one-use database records. Protected routes use current stored roles and approval; admin changes include the displayed record revision.

The existing case, enrollment and extraction paths remain. Fine-grained case/study policy is separate work.
Keep extraction, database and Grafana backends private. Grafana should use this BFF's `/api/me` for current session authority.

Verification: `npm run typecheck`, `npm test`, and the real PostgreSQL/BFF integration test listed in the branch guide.
