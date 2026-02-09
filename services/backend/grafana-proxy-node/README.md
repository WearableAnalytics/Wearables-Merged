# Grafana proxy (Node)

This service forwards Grafana requests and injects a signed JWT for Grafana auth.

## How it works
- Frontend iframe points at the proxy embed endpoint (default `/grafana/embed?deviceId=<caseToken>`).
- Proxy forwards to Grafana and injects `X-JWT-Assertion: <signed-token>`.
- Proxy builds the dashboard URL server-side using `GRAFANA_DASHBOARD_ID`, `GRAFANA_DASHBOARD_DATASOURCE`, and `GRAFANA_ORG_ID`.
- Proxy always appends `kiosk` (full kiosk mode) and `_dash.hide*` flags to suppress dashboard chrome in the iframe.
- Proxy blocks HTML navigation to Grafana pages outside the configured dashboard UID.
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
- `GRAFANA_DASHBOARD_ID`: dashboard UID used by `/grafana/embed`.
- `GRAFANA_DASHBOARD_DATASOURCE`: datasource variable value used by `/grafana/embed` as `var-DS_INFLUXDB`.
- `APP_JWT_SECRET`: secret used to verify your app session JWT cookie.
- `SESSION_COOKIE_NAME`: session cookie name (defaults to `jwt`).
- `GRAFANA_JWT_SUBJECT`: fallback subject claim when no valid session cookie is present.

See `.env.example` for all settings.

## Grafana config
- Enable JWT auth and point Grafana at the public key that matches your private key.
- Allow embedding so the iframe can load.
