# Wearables Web Containers

## Run locally with Docker Compose
- From the repo root: `cd services/web`
- With logs in the foreground: `docker compose up --build web`
- Detached (no logs in the terminal): `docker compose up --build -d web`
- Env: set `VITE_API_BASE_URL` in a `.env` next to `docker-compose.yml` (defaults to `http://localhost:3001/api`). Compose passes it as a build arg.
- Required for Docker builds: `VITE_GRAFANA_PROXY_URL=http://localhost:3002/grafana` to control the Grafana iframe source.

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
