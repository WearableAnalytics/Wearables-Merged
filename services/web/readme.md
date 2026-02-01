# Wearables Web Containers

## Run locally with Docker Compose
- From the repo root: `cd services/web`
- With logs in the foreground: `docker compose up --build web`
- Detached (no logs in the terminal): `docker compose up --build -d web`
- Env: set `VITE_API_BASE_URL` in a `.env` next to `docker-compose.yml` (defaults to `http://localhost:3001/api`). Compose passes it as a build arg.
- Optional: `VITE_GRAFANA_PROXY_URL=http://localhost:3002/grafana` to control the Grafana iframe source (defaults to `http://localhost:3002/grafana`).

## Build a single image (for Kubernetes or manual runs)
- Build from repo root: `docker build -f services/web/Dockerfile -t wearables-web --build-arg VITE_API_BASE_URL=https://api.example.com .`
- Run: `docker run -p 8080:80 wearables-web`

## API URL notes
- `VITE_API_BASE_URL` is baked into the frontend at build time; runtime env vars are not read by the image.
- For Kubernetes, route `/api` to the backend and rebuild with the backend URL you want baked in (or add a runtime config layer if needed later).
