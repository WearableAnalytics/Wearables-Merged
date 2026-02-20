# Wearables BFF

Backend-for-frontend service for the Wearables web app.

## What It Does

- Auth/session handling for web clients (cookie-based session JWT).
- Login and registration flows (including magic-link verification).
- User self-service endpoints (`/me`, role/admin requests).
- Patient/case APIs used by the frontend.
- Case-token issuance and verification.
- Admin workflows for user/access review.

## Runtime Notes

- Route base is `{API_PREFIX}`.
- Some stores are in-memory (user state, magic-link tokens, case-token metadata), so they reset on restart.
- Patient/case data comes from mock data or external database API depending on `USE_MOCK_DATA`.

## API Surface

Main route groups under `{API_PREFIX}`:

- Health: `/health`
- Auth: `/login`, `/register`, `/verify-magiclink`, `/logout`
- User: `/me`, `/request-admin`, `/request-role`
- Patient/case: `/hospital/*`, `/patients*`, `/cases*`
- Admin: `/admin/*`

For the exact contract, use the generated OpenAPI schema in `services/packages/api-schema`.

## Configuration

Use `.env.example` as the source of truth for runtime variables.  
Startup validation is enforced in `src/config.ts`.

Compatibility requirement with Grafana proxy:

- BFF `JWT_SECRET` must match proxy `APP_JWT_SECRET`.
- BFF `TOKEN_ISSUER` must match proxy `APP_JWT_ISSUER`.

## Local Run

```bash
npm install
cp .env.example .env
npm run dev
```

## Docker

- Dockerfile: `services/backend/wearables-bff/Dockerfile`

## Kubernetes

In Kubernetes, set runtime values via Helm values/Secrets for this service (not local `.env`).

## Regenerate API Artifacts

```bash
npm run generate:api
```
