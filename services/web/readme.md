# Wearables Web Containers

## Local development (without Docker)
- From repo root: `cd services/web`
- Install deps: `npm install`
- Run web + backend: `npm run dev`
- Run only web (Vite): `npm run dev:web`
- Run only backend: `npm run dev:backend`

## Environment variables
- Frontend variables prefixed with `VITE_` are bundled into client code and visible in the browser.
- Never place private keys, service credentials, or secrets in `VITE_*` variables.

### Variables used by this service
1. `VITE_API_BASE_URL`
- Used by API clients in `src/api/defaultApi.ts` and `src/api/index.ts`.
- Default: `/api` (or `http://localhost:3001/api` in local Docker usage).
- Build-time variable for production bundles.
2. `VITE_GRAFANA_PROXY_URL`
- Used by `src/pages/case/CasePage.tsx` to build Grafana iframe URLs.
- Example: `http://localhost:3002/grafana`.
- Required if you use the case monitoring dashboard.
3. `WEB_DEV_BACKEND_HEALTH_URL`
- Used by `scripts/dev-with-backend.mjs` when running `npm run dev`.
- Default: `http://localhost:3001/api/health`.
- Optional override for custom backend health endpoints.
4. `VITE_SOCKET_URL` (currently optional)
- Referenced by `src/socket.ts`.
- This socket module is not currently imported by app pages/components.

## Run locally with Docker Compose
- From the repo root: `cd services/web`
- With logs in the foreground: `docker compose up --build web`
- Detached (no logs in the terminal): `docker compose up --build -d web`
- Env: set `VITE_API_BASE_URL` and `VITE_GRAFANA_PROXY_URL` in a `.env` next to `docker-compose.yml`. Compose passes both as build args.

## Build a single image (for Kubernetes or manual runs)
- Build from repo root: `docker build -f services/web/Dockerfile -t wearables-web --build-arg VITE_API_BASE_URL=https://api.example.com .`
- Run: `docker run -p 8080:80 wearables-web`

## API URL notes
- `VITE_API_BASE_URL` is baked into the frontend at build time; runtime env vars are not read by the image.
- For Kubernetes, route `/api` to the backend and rebuild with the backend URL you want baked in (or add a runtime config layer if needed later).

## Branding logos
- Logo files should be managed under `services/web/src/assets/branding/logos`.
- Two logo classes are used:
1. `square`: compact logo mark, also used as favicon.
2. `horizontal`: wide logo, used in the navbar header.

### Structure and naming
- Place files using this structure:
1. `services/web/src/assets/branding/logos/square/light.<ext>`
2. `services/web/src/assets/branding/logos/square/dark.<ext>` (optional)
3. `services/web/src/assets/branding/logos/horizontal/light.<ext>`
4. `services/web/src/assets/branding/logos/horizontal/dark.<ext>` (optional)
- Supported extensions: `png`, `jpg`, `jpeg`, `svg`, `webp`, `avif`, `gif`, `ico`.

### Optional files and fallback generation
- Dark variants are optional.
- If a variant for the active theme is missing, the app uses the available opposite-theme asset without additional runtime styling or contrast correction.

### Favicon derivation
- Favicon is derived from the `square` logo class.
- If both `square/light` and `square/dark` exist, favicon always uses `square/light`.
- If only one square asset exists, favicon uses that available asset.

### Current migration mapping
- Existing files mapped into the new structure:
1. `W.png` -> `services/web/src/assets/branding/logos/square/light.png`
2. `Wearables.png` -> `services/web/src/assets/branding/logos/horizontal/light.png`
