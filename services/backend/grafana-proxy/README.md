# Grafana proxyx

This service forwards Grafana requests and injects a signed JWT for Grafana auth.

## How it works
- Frontend iframe points at the proxy embed endpoint (default `/grafana/embed?deviceId=<caseToken>&dashboardUid=<uid>&from=<time>&to=<time>`).
- Proxy forwards to Grafana and injects `X-JWT-Assertion: <signed-token>`.
- Proxy builds the dashboard URL server-side using `dashboardUid`, `GRAFANA_ALLOWED_DASHBOARD_IDS`, `GRAFANA_DASHBOARD_DATASOURCE`, and `GRAFANA_ORG_ID`.
- `/embed` accepts optional `from` and `to` query params (Grafana relative times like `now-24h`, epoch ms, or ISO date/time). Defaults are `from=now-24h` and `to=now`.
- `/embed` also accepts optional `viewPanel=<panel-id>` to open a single panel/tile in the dashboard route.
- `/embed` requires `dashboardUid=<uid>` and only allows UIDs listed in `GRAFANA_ALLOWED_DASHBOARD_IDS`.
- Proxy always appends `kiosk` (full kiosk mode) and `_dash.hide*` flags to suppress dashboard chrome in the iframe.
- Proxy blocks HTML navigation to Grafana pages outside the allowed dashboard UID list.
- Header value prefix is supported via `GRAFANA_JWT_HEADER_VALUE_PREFIX` (for example `Bearer`).
- If `SESSION_COOKIE_NAME` and `APP_JWT_SECRET` are set, the proxy derives Grafana JWT claims from the app session cookie.
- If the session cookie is missing/invalid, it falls back to static `GRAFANA_JWT_*` claims.

## Quick start
```
cp .env.example .env
npm install
npm run dev
```

## Required env
- `GRAFANA_JWT_PRIVATE_KEY` or `GRAFANA_JWT_PRIVATE_KEY_PATH`: private key used to sign JWTs.
- `GRAFANA_BASE_URL`: Grafana base URL (can include `/grafana` if hosted on a subpath).
- `GRAFANA_ALLOWED_DASHBOARD_IDS`: comma-separated dashboard UIDs allowed for `/embed?dashboardUid=...`.
- `GRAFANA_DASHBOARD_DATASOURCE`: datasource variable value used by `/grafana/embed` as `var-DS_INFLUXDB`.
- `APP_JWT_SECRET`: secret used to verify your app session JWT cookie.
- `SESSION_COOKIE_NAME`: session cookie name (defaults to `jwt`).
- `GRAFANA_JWT_SUBJECT`: fallback subject claim when no valid session cookie is present.

See `.env.example` for all settings.

## Grafana config
- Enable JWT auth and point Grafana at the public key that matches your private key.
- Allow embedding so the iframe can load.
