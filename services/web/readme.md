# Wearables Web – Containers

## Single image (Kubernetes-friendly)
- Build (run from repo root): `docker build -f services/web/Dockerfile -t wearables-web --build-arg VITE_API_BASE_URL=https://api.example.com .`
- Run: `docker run -p 8080:80 wearables-web`
- Deploy separately to Kubernetes behind an Ingress that routes `/` to this service and `/api` to the backend. Set `VITE_API_BASE_URL` at build time to the backend URL you want baked into the bundle.
- Env file option: create `services/web/.env.production` with `VITE_API_BASE_URL=...`; the Docker build will read it when it runs `npm run build`.

## Local with Docker Compose
- Compose file: `docker-compose.yml` builds the same web image.
- `VITE_API_BASE_URL` is passed as a build-arg. Set it in a `.env` next to `docker-compose.yml`, e.g. `VITE_API_BASE_URL=http://backend:3001` (or `http://host.docker.internal:3001` if your API runs on the host).
- Run: `docker compose up --build web` (frontend at http://localhost:8080).
- Add your backend as another Compose service named `backend` so the default `http://backend:3001` works, or point `VITE_API_BASE_URL` to whatever backend you run.

## API URL behavior
- `VITE_API_BASE_URL` is compiled into the frontend bundle during `npm run build`; the image does not auto-read runtime env vars for it.
- Kubernetes: keep frontend and backend as separate services; let the Ingress/Gateway route `/api` to the backend. Rebuild with the correct API URL (or add a runtime config layer later if you want to avoid rebuilds per environment).
