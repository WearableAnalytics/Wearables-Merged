# Wearables Backend API (Node.js)

Express backend used by the Wearables frontend.

Despite the folder name, this service is not only registration. It currently handles:

- Cookie-based authentication (`jwt`)
- Email magic-link login (or direct auth in development / mailer-disabled mode)
- User onboarding and approval states (`pending`, `approved`, `denied`)
- Admin workflows (user approval, role/status management, admin-request review)
- Patient and case endpoints used by the frontend
- Case creation from Hospital case IDs
- Case token verification

## Runtime model

- Auth and user/admin state are stored in memory (`src/services/userStore.ts`).
- Magic-link tokens are stored in memory (`src/api/routes/auth.ts`).
- Case tokens are JWTs with an in-memory metadata store (`src/services/tokenService.ts`).
- Patient/case data can come from mock data (`USE_MOCK_DATA=true`, `src/mockData.ts`) or the external database API (`USE_MOCK_DATA=false`, `src/clients/databaseApi.ts`).
- Hospital case lookup currently uses local mock data in both modes (`src/services/index.ts`).

Important: in-memory stores are reset on process restart.

## Run locally

```bash
cd services/backend/registration-service-node
npm install
cp .env.example .env
npm run dev
```

Frontend should point to this backend, for example:

```bash
VITE_API_BASE_URL=http://localhost:3001
```

## Environment variables

From `.env.example` plus runtime behavior in `src/config.ts` and `src/api/routes/auth.ts`:

- `PORT` (default `3001`)
- `NODE_ENV` (`development` or `production`)
- `API_PREFIX` (default `/api`, trailing slash removed automatically)
- `FRONTEND_URL` (comma-separated allowed origins for CORS + frontend redirects)
- `BACKEND_URL` (base URL for generated magic links)
- `JWT_SECRET` (required for stable token behavior)
- `ADMIN_EMAILS` (comma-separated bootstrap admin emails)
- `DATABASE_API_URL` (external patient/case API)
- `DATABASE_API_TIMEOUT` (ms)
- `USE_MOCK_DATA` (`true` or `false`)
- `LOG_LEVEL` (`trace` | `debug` | `info` | `warn` | `error`)
- `MAILER_ENABLED` (`false` is blocked in production)
- `MAILER_FROM_NAME`
- `MAILER_FROM_EMAIL`
- `BREVO_API_KEY` (required to send real emails)
- `COOKIE_SECURE` (optional: force cookie `secure` true/false)

## API surface

All routes are mounted under `{API_PREFIX}`.

Public / bootstrap:

- `GET {API_PREFIX}/health`
- `POST {API_PREFIX}/login`
- `POST {API_PREFIX}/register`
- `GET {API_PREFIX}/verify-magiclink?token=...`
- `POST {API_PREFIX}/logout`

Authenticated:

- `GET {API_PREFIX}/me`
- `POST {API_PREFIX}/request-admin`
- `GET {API_PREFIX}/hospital/cases/:hospitalCaseId`
- `GET {API_PREFIX}/patients`
- `GET {API_PREFIX}/patients/:patientId`
- `GET {API_PREFIX}/patients/:patientId/cases`
- `GET {API_PREFIX}/cases`
- `GET {API_PREFIX}/cases/:caseId`
- `POST {API_PREFIX}/cases/from-hospital-case`
- `POST {API_PREFIX}/cases/verify-token`

Admin only:

- `GET {API_PREFIX}/admin/pending-users`
- `GET {API_PREFIX}/admin/approved-users`
- `GET {API_PREFIX}/admin/denied-users`
- `GET {API_PREFIX}/admin/pending-admin-requests`
- `POST {API_PREFIX}/admin/users/:userId/approve`
- `POST {API_PREFIX}/admin/users/:userId/deny`
- `POST {API_PREFIX}/admin/users/:userId/unblock`
- `POST {API_PREFIX}/admin/users/:userId/approve-admin`
- `POST {API_PREFIX}/admin/users/:userId/deny-admin`
- `PATCH {API_PREFIX}/admin/users/:userId`

## Keep API typings in sync

Regenerate API schema/client after OpenAPI changes:

```bash
npm run generate:api
```

This rebuilds `packages/api-schema/openapi.json` and regenerates `src/api/openapi-client`.
