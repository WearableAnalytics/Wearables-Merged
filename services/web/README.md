# Wearables Web Frontend

React + Vite frontend for the Wearables platform.

## Scope

This README documents the frontend source behavior in `services/web`.
Kubernetes deployment behavior is documented in `gitops/apps/web-frontend/README.md`.

## What This App Does

- Renders auth, case management, and monitoring UI.
- Calls BFF APIs through the generated OpenAPI client and custom auth endpoints.
- Embeds Grafana dashboards on the case page through `${GRAFANA_PROXY_URL}/embed`.

## Runtime Config In The Code

Runtime values are resolved in this order (`src/config/runtimeConfig.ts`):

1. `window.__APP_CONFIG__` from `/runtime-config.js`
2. `VITE_*` values from Vite env files

`index.html` loads `/runtime-config.js` before the app bundle, so `window.__APP_CONFIG__` is available at startup.

Required runtime keys:

- `API_BASE_URL`
- `GRAFANA_PROXY_URL`

If required values are missing, the app throws a startup error.

For variable descriptions and examples, use:

- `services/web/.env.example`
- `gitops/apps/web-frontend/values.yaml`

## Local Development

```bash
npm install
npm run dev
```

Useful scripts:

- `npm run dev` -> starts backend and frontend (`scripts/dev-with-backend.mjs`)
- `npm run dev:web` -> starts only the Vite frontend
- `npm run build` -> type-check + production build
- `npm run lint` -> lint the frontend
- `npm run generate:api` -> regenerate `src/api/openapi-client`

## Key Files

- App bootstrap: `services/web/src/main.tsx`
- Runtime config resolver: `services/web/src/config/runtimeConfig.ts`
- API wiring: `services/web/src/api/defaultApi.ts`
- Case monitoring + Grafana embed usage: `services/web/src/pages/case/CasePage.tsx`
- Dev proxy and env loading: `services/web/vite.config.ts`
- Container serving config: `services/web/Dockerfile`, `services/web/nginx.conf`

## Security Note

Do not put secrets in frontend config. Values in `runtime-config.js` and `VITE_*` are public in the browser.
