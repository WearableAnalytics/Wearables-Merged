# API Schema

`src/schemas.ts` is the single source of truth (Zod + `zod-to-openapi`).

## Generate OpenAPI Schema

From this package directory:

```bash
npm run generate:api-schema
```

This generates `openapi.json`.

## Scope

This package describes the patient/case API contract used by `wearables-bff`.
It currently includes:

- `GET /hospital/cases/{hospitalCaseId}`
- `GET /patients`
- `GET /patients/{patientId}`
- `GET /patients/{patientId}/cases`
- `GET /cases`
- `GET /cases/{caseId}`
- `POST /cases/from-hospital-case`
- `POST /cases/verify-token`
- `GET /researcher/api-tokens`, `POST /researcher/api-tokens`, `POST /researcher/api-tokens/{tokenId}/revoke`

This package does not currently model all auth/admin routes exposed by the backend
(for example `/login`, `/register`, `/admin/...`).

Case status note:

- `src/schemas.ts` models case status as `active | inactive`.
- `wearables-bff` normalizes non-mock database status values to this contract before returning responses.

For full backend runtime and route documentation, see:

- `services/backend/wearables-bff/README.md`

For Kubernetes deployment/configuration of `wearables-bff`, see:

- `gitops/apps/services/wearables-bff/README.md`
