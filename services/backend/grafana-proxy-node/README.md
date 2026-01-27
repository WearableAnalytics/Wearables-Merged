# Grafana proxy (Node)

This service validates the existing registration-service session cookie locally, issues a short-lived Grafana JWT, and injects it into proxied requests as `X-JWT-Assertion`.

## How it works
- Frontend iframe points at the proxy (default `/grafana`).
- Proxy validates the `jwt` cookie (shared secret with registration service).
- Proxy signs a Grafana JWT (RS256) and injects `X-JWT-Assertion` when forwarding to Grafana.
- Grafana verifies the JWT using the JWKS served by this proxy.

## Quick start
```
cp .env.example .env
npm install
npm run dev
```

## Grafana config (example)
```
[auth.jwt]
enabled = true
header_name = X-JWT-Assertion
jwk_set_url = https://your-proxy.example.com/.well-known/jwks.json
username_claim = sub
email_claim = email
role_attribute_path = role

[security]
allow_embedding = true
```

## Required env
- `APP_JWT_SECRET`: same as registration-service-node `JWT_SECRET`.
- `GRAFANA_JWT_PRIVATE_KEY` or `GRAFANA_JWT_PRIVATE_KEY_PATH`: PEM private key for signing Grafana JWTs.

See `.env.example` for all settings.
