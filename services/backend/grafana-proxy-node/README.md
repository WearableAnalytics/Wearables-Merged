# Grafana proxy (Node)

This service forwards Grafana requests and injects a Grafana service account token as a Bearer auth header.

## How it works
- Frontend iframe points at the proxy (default `/grafana`).
- Proxy forwards to Grafana and injects `Authorization: Bearer <service-account-token>`.

## Quick start
```
cp .env.example .env
npm install
npm run dev
```

## Required env
- `GRAFANA_SERVICE_ACCOUNT_TOKEN`: Grafana service account token with dashboard access.
- `GRAFANA_BASE_URL`: Grafana base URL (can include `/grafana` if hosted on a subpath).

See `.env.example` for all settings.
