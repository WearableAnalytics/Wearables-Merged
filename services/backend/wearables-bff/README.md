# Wearables Backend For Frontend (Node.js)

Express backend used by the Wearables frontend.

This backend-for-frontend currently handles:

- Cookie-based authentication (`jwt`)
- Email magic-link login (or direct auth outside production)
- User onboarding and approval states (`pending`, `approved`, `denied`)
- Admin workflows (user approval, role/status management, admin-request review)
- Patient and case endpoints used by the frontend
- Case creation from Hospital case IDs
- Case token verification

## Documentation map

- Local runtime behavior, env vars, and API routes: this file
- Frontend runtime config and local web setup: `services/web/readme.md`
- Helm/Kubernetes deployment for this service: `gitops/apps/services/wearables-bff/README.md`
- Multi-service runtime deployment (BFF + Grafana proxy + frontend): `docs/deploy-runtime-config.md`
- Patient/case OpenAPI contract: `services/packages/api-schema/README.md`

## Runtime model

- Auth and user/admin state are stored in memory (`src/services/userStore.ts`).
- Magic-link tokens are stored in memory (`src/api/routes/auth.ts`).
- Case tokens are mock string tokens in mock mode (`src/mockData.ts`) and JWT-backed in non-mock mode with an in-memory metadata store (`src/services/tokenService.ts`).
- Patient/case data can come from mock data (`USE_MOCK_DATA=true`, `src/mockData.ts`) or the external database API (`USE_MOCK_DATA=false`, `src/clients/databaseApi.ts`).
- Non-mock case statuses are normalized to `active`/`inactive` before responses are returned.
- Hospital case lookup currently uses local mock data in both modes (`src/services/index.ts`).

Important: in-memory stores are reset on process restart.

## Run locally

```bash
cd services/backend/wearables-bff
npm install
cp .env.example .env
npm run dev
```

`.env.example` already includes all required frontend/database env vars, so local startup works directly after copying it.

Frontend local dev should proxy API requests to this backend. In `services/web/.env`:

```bash
VITE_API_BASE_URL=/api
VITE_BACKEND_URL=http://localhost:3001
```

See `services/web/readme.md` for frontend runtime config details.

To run against the real database API instead of mocks, set at least:

- `USE_MOCK_DATA=false`
- `JWT_SECRET=...`

Docker quick start from `services/backend/wearables-bff`:

```bash
docker build -t wearables-bff .
docker run --rm -p 3001:3001 --env-file .env wearables-bff
```

## Kubernetes vs local `.env`

- Local `npm run dev`: uses `.env` in this folder.
- Kubernetes deployment: does not use this `.env` file.
- In Kubernetes, set runtime values in `gitops/apps/services/wearables-bff/values.yaml`.
- Provide secrets either via `scripts/bootstrap-runtime-secrets.sh` (recommended) or via chart-managed/existing Secret settings (`secret.*`) in the Helm chart.
- See `docs/deploy-runtime-config.md` for the full deploy flow.

## Environment variables

From `.env.example` plus runtime behavior in `src/config.ts` and `src/api/routes/auth.ts`:

- `PORT` (required; positive integer)
- `NODE_ENV` (required; `development` or `production`)
- `API_PREFIX` (required; must start with `/`; trailing slash removed automatically)
- `FRONTEND_ORIGINS` (required; comma-separated allowed origins for CORS; no fallback)
- `FRONTEND_REDIRECT_URL` (required; single frontend base URL used for redirects and approval email links; no fallback)
- `BACKEND_URL` (required; absolute base URL used for generated magic links)
- `JWT_SECRET` (required in production; required for non-mock case-token generation/verification; cannot be `dev-secret` in production; in dev+mock mode it may be omitted and falls back to `dev-secret`; when used with Grafana proxy session identity, keep equal to proxy `APP_JWT_SECRET`)
- `RESEARCHER_API_ACCESS_TOKEN` (required; token returned by researcher/admin token endpoint)
- `AUTH_SESSION_EXPIRY_SECONDS` (optional; positive integer in seconds; default `604800`)
- `MAGIC_LINK_EXPIRY_SECONDS` (optional; positive integer in seconds; default `900`)
- `CASE_TOKEN_EXPIRY_SECONDS` (optional; positive integer in seconds; default `691200`)
- `TOKEN_ISSUER` (optional; JWT issuer for case tokens; default `wearables-bff`)
- `ADMIN_EMAILS` (comma-separated bootstrap admin emails)
- `DATABASE_API_URL` (required; external patient/case API base URL; no fallback)
- `DATABASE_API_TIMEOUT` (required; positive integer in ms; no fallback)
- `USE_MOCK_DATA` (required; `true` or `false`)
- `LOG_LEVEL` (required; `trace` | `debug` | `info` | `warn` | `error`)
- `MAILER_FROM_NAME` (required when `NODE_ENV=production`)
- `MAILER_FROM_EMAIL` (required when `NODE_ENV=production`)
- `BREVO_API_KEY` (required when `NODE_ENV=production`)
- `COOKIE_SECURE` (optional; if set must be exactly `true` or `false`)

## API surface

All routes are mounted under `{API_PREFIX}`.

Public / bootstrap:

- `GET {API_PREFIX}/health`
- `POST {API_PREFIX}/login`
- `POST {API_PREFIX}/register`
- `GET {API_PREFIX}/verify-magiclink?token=...`
- `POST {API_PREFIX}/logout`

Authenticated (`auth.required`):

- `GET {API_PREFIX}/me`
- `POST {API_PREFIX}/request-admin`
- `POST {API_PREFIX}/request-role`

Researcher or admin:

- `GET {API_PREFIX}/researcher/api-access-token`

Practitioner or admin:

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
- `GET {API_PREFIX}/admin/pending-access-requests`
- `POST {API_PREFIX}/admin/users/:userId/approve`
- `POST {API_PREFIX}/admin/users/:userId/deny`
- `POST {API_PREFIX}/admin/users/:userId/unblock`
- `POST {API_PREFIX}/admin/users/:userId/approve-admin`
- `POST {API_PREFIX}/admin/users/:userId/deny-admin`
- `POST {API_PREFIX}/admin/users/:userId/approve-role`
- `POST {API_PREFIX}/admin/users/:userId/deny-role`
- `POST {API_PREFIX}/admin/users/:userId/review-request`
- `PATCH {API_PREFIX}/admin/users/:userId`

## Keep API typings in sync

Regenerate API schema/client after OpenAPI changes:

```bash
npm run generate:api
```

This rebuilds `packages/api-schema/openapi.json` and regenerates `src/api/openapi-client`.
