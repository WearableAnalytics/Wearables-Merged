# Grafana Proxy Helm Chart

Helm chart to deploy the `grafana-proxy` service.

## What This Chart Manages

- Deployment, Service, ConfigMap, and Secret wiring for `grafana-proxy`.
- Runtime env injection from:
  - `values.yaml` (`proxy.*`, `session.*`, `grafana.*`) via ConfigMap.
  - Secret (`secret.*`) via Secret reference.

Service runtime behavior is documented in `services/backend/grafana-proxy/README.md`.

## Required Secret Keys

The runtime Secret must contain:

- `GRAFANA_JWT_PRIVATE_KEY`
- `APP_JWT_SECRET`

Recommended bootstrap:

```bash
./scripts/bootstrap-runtime-secrets.sh
```

## Critical Alignment

- `proxy.prefix` must match frontend `GRAFANA_PROXY_URL` path.
- `APP_JWT_SECRET` must match BFF `JWT_SECRET`.
- `session.jwtIssuer` must match BFF `TOKEN_ISSUER`.
- `grafana.allowedDashboardIds` must include all dashboard UIDs used by the frontend.

## Important Notes

- This chart does not create ingress resources.
- `proxy.prefix` controls only the in-app mount path, not external routing.
- `secret.create: false` requires an existing Secret (`secret.name` or `<release>-secrets`).
- `configMap.create: false` requires an existing ConfigMap (`configMap.name` or `<release>-config`).
- The proxy does not expose `/.well-known/jwks.json`; if Grafana uses `GF_AUTH_JWT_JWK_SET_URL`, point it to an external JWKS provider.

## Deploy

```bash
helm upgrade --install grafana-proxy ./gitops/apps/monitoring/grafana-proxy \
  -n monitoring \
  --create-namespace \
  --set secret.name=grafana-auth-secrets \
  -f ./gitops/apps/monitoring/grafana-proxy/values.yaml
```
