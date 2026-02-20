# Grafana Proxy

Reverse proxy for Grafana with JWT-based auth and a dedicated embed endpoint.

## What It Does

- Proxies requests to Grafana and injects a proxy-signed JWT.
- Exposes `GET /health`.
- Exposes `GET <PROXY_PREFIX>/embed` for iframe/dashboard embedding.

## Embed Contract

`GET <PROXY_PREFIX>/embed?deviceId=<caseToken>&dashboardUid=<uid>[&from=...&to=...&theme=light|dark]`

- `deviceId` may be either:
  - a wearables-bff case token JWT (`type=case-verification`), or
  - an opaque device identifier string (non-empty, no whitespace).
- `dashboardUid` must be allowlisted.
- `from` / `to` accept Grafana relative time, epoch, or ISO datetime.
- `theme` supports `light` or `dark`.

Behavior:

- Requires a valid app session cookie.
- If `deviceId` is a valid case token JWT, resolves `var-deviceId` from token `patientId`.
- Otherwise forwards `deviceId` as-is to Grafana variable `var-deviceId`.
- Redirects to the Grafana dashboard URL with kiosk/hide flags for embedding.

Errors:

- `400`: invalid/missing embed params
- `401`: missing/invalid session
- `500`: missing required embed configuration

## Runtime Prerequisites

Proxy routes are mounted only if Grafana target, Grafana JWT signing key, and app JWT secret are configured. Otherwise only `/health` is available.

## Configuration

Use `.env.example` as the source of truth for runtime variables.

## Grafana Requirements

- JWT auth must trust the public key matching the proxy private key.
- Embedding must be enabled.
- If Grafana uses `GF_AUTH_JWT_JWK_SET_URL`, point it to an external JWKS provider (this service does not expose `/.well-known/jwks.json`).

## Local Run

```bash
cp .env.example .env
npm install
npm run dev
```
