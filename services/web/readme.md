# Wearables Web Frontend

React + Vite frontend for the Wearables platform.

## What It Does

- Provides the web UI for auth, case management, and monitoring.
- Calls backend APIs via `API_BASE_URL`.
- Loads Grafana dashboards through `${GRAFANA_PROXY_URL}/embed`.

## Runtime Config

Runtime values are resolved in this order:

1. `window.__APP_CONFIG__` (`/runtime-config.js`)
2. `VITE_*` build-time vars
3. internal defaults

Use `public/runtime-config.js` and `src/config/runtimeConfig.ts` as the source of truth for frontend runtime keys/defaults.

## Integration Contract

- `API_BASE_URL` must point to the BFF API base path.
- `GRAFANA_PROXY_URL` must point to the Grafana proxy mount path.
- Case monitoring embeds rely on proxy `/embed` with case-token-based `deviceId`.

## Local Run

```bash
npm install
npm run dev
```

## Docker

- Dockerfile: `services/web/Dockerfile`
- Compose setup: `services/web/docker-compose.yml`
- Nginx runtime/proxy config: `services/web/nginx.conf`

## Configuration

Do not store secrets in frontend runtime config; it is public in the browser.

## Regenerate API Client

```bash
npm run generate:api
```
