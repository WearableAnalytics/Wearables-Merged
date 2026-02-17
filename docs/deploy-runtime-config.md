# Runtime Config/Secret Deployment (Kubernetes)

This repo is configured so `wearables-bff`, `grafana-proxy`, and frontend apps are deployed with runtime config/secrets, not Docker-baked secrets.

## Do I still need `.env` files?

For Kubernetes deployment: no.

- `wearables-bff` runtime config comes from `gitops/apps/services/wearables-bff/values.yaml` (`env`) and Secret values from `bootstrap-runtime-secrets.sh`.
- `grafana-proxy` runtime config comes from `gitops/apps/monitoring/grafana-proxy/values.yaml` and Secret values from `bootstrap-runtime-secrets.sh`.
- frontend runtime config comes from Helm values (`runtimeConfig.*`) and is mounted as `runtime-config.js`.

For local development without Kubernetes: yes.

- `services/backend/wearables-bff/.env` is used by `npm run dev`.
- `services/backend/grafana-proxy/.env` is used by `npm run dev`.
- `services/web/.env` is used as local fallback in Vite dev.

## Where to change what

- Bootstrap admin emails: `gitops/apps/services/wearables-bff/values.yaml` -> `env.ADMIN_EMAILS`
- BFF environment mode: `gitops/apps/services/wearables-bff/values.yaml` -> `env.NODE_ENV`
- BFF mailer sender: `gitops/apps/services/wearables-bff/values.yaml` -> `env.MAILER_FROM_*`
- BFF/Grafana shared JWT and API keys: `./scripts/bootstrap-runtime-secrets.sh`
- Grafana proxy runtime settings: `gitops/apps/monitoring/grafana-proxy/values.yaml`
- Frontend API/proxy URLs: `gitops/apps/web/values.yaml` or `gitops/apps/web-frontend/values.yaml` (`runtimeConfig.*`)

## 1. Bootstrap runtime secrets

Run once (or re-run whenever needed):

```bash
./scripts/bootstrap-runtime-secrets.sh
```

Optional overrides:

```bash
BREVO_API_KEY='<brevo-api-key>' \
RESEARCHER_API_ACCESS_TOKEN='<researcher-token>' \
GRAFANA_JWT_PRIVATE_KEY_PATH='./secrets/grafana-jwt-private.pem' \
./scripts/bootstrap-runtime-secrets.sh
```

This script:

- creates namespaces if missing
- ensures one shared JWT secret is used by both BFF and Grafana proxy
- applies `wearables-bff-secrets` in namespace `wearables-bff`
- applies `grafana-auth-secrets` in namespace `monitoring`

## 2. Deploy wearables-bff

```bash
helm upgrade --install wearables-bff ./gitops/apps/services/wearables-bff \
  -n wearables-bff --create-namespace \
  -f ./gitops/apps/services/wearables-bff/values.yaml
```

## 3. Deploy grafana-proxy

```bash
helm upgrade --install grafana-auth ./gitops/apps/monitoring/grafana-proxy \
  -n monitoring --create-namespace \
  -f ./gitops/apps/monitoring/grafana-proxy/values.yaml
```

## 4. Deploy frontend

Choose one frontend chart (`web` or `web-frontend`).

`web`:

```bash
helm upgrade --install wearables-web ./gitops/apps/web \
  -n web --create-namespace \
  -f ./gitops/apps/web/values.yaml
```

`web-frontend`:

```bash
helm upgrade --install web-frontend ./gitops/apps/web-frontend \
  -n web-frontend --create-namespace \
  -f ./gitops/apps/web-frontend/values.yaml
```

Both charts mount `runtime-config.js` from a ConfigMap at runtime.
