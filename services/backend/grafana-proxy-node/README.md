# Grafana proxy (Node)

This service forwards Grafana requests and injects a signed JWT for Grafana auth.

## How it works
- Frontend iframe points at the proxy (default `/grafana`).
- Proxy forwards to Grafana and injects `X-JWT-Assertion: <signed-token>`.

## Quick start
```
cp .env.example .env
npm install
npm run dev
```

## Required env
- `GRAFANA_JWT_PRIVATE_KEY` or `GRAFANA_JWT_PRIVATE_KEY_PATH`: private key used to sign JWTs.
- `GRAFANA_JWT_SUBJECT`: subject claim used by Grafana to identify the user.
- `GRAFANA_BASE_URL`: Grafana base URL (can include `/grafana` if hosted on a subpath).

See `.env.example` for all settings.

## Grafana config
- Enable JWT auth and point Grafana at the public key that matches your private key.
- Allow embedding so the iframe can load.
