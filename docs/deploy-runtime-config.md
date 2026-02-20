# Runtime Config/Secret Deployment (Kubernetes)

This repo is configured so `wearables-bff`, `grafana-proxy`, and frontend apps are deployed with runtime config/secrets, not Docker-baked secrets.

Use this guide when deploying multiple components together.
If you only deploy one component, start with that chart README:

- Frontend source/runtime behavior: `services/web/readme.md`
- `gitops/apps/services/wearables-bff/README.md`
- `gitops/apps/monitoring/grafana-proxy/README.md`
- `gitops/apps/web-frontend/README.md` (preferred) or `gitops/apps/web/README.md`

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
- BFF frontend CORS origins: `gitops/apps/services/wearables-bff/values.yaml` -> `env.FRONTEND_ORIGINS`
- BFF frontend redirect base URL: `gitops/apps/services/wearables-bff/values.yaml` -> `env.FRONTEND_REDIRECT_URL`
- BFF backend public URL (magic-link verification links): `gitops/apps/services/wearables-bff/values.yaml` -> `env.BACKEND_URL`
- BFF environment mode: `gitops/apps/services/wearables-bff/values.yaml` -> `env.NODE_ENV`
- BFF mailer sender: `gitops/apps/services/wearables-bff/values.yaml` -> `env.MAILER_FROM_*`
- BFF/Grafana shared JWT and API keys: `./scripts/bootstrap-runtime-secrets.sh`
- Grafana proxy runtime settings: `gitops/apps/monitoring/grafana-proxy/values.yaml`
- Grafana proxy public path: keep `gitops/apps/monitoring/grafana-proxy/values.yaml` `proxy.prefix` aligned with frontend `runtimeConfig.grafanaProxyUrl` and your external route
- Frontend API/proxy URLs: `gitops/apps/web/values.yaml` or `gitops/apps/web-frontend/values.yaml` (`runtimeConfig.*`)

## 1. Bootstrap runtime secrets

Run once (or re-run whenever needed):

```bash
./scripts/bootstrap-runtime-secrets.sh
```

Required/optional overrides:

```bash
RESEARCHER_API_ACCESS_TOKEN='<researcher-token>' \
BREVO_API_KEY='<brevo-api-key>' \
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
helm upgrade --install grafana-proxy ./gitops/apps/monitoring/grafana-proxy \
  -n monitoring --create-namespace \
  --set secret.name=grafana-auth-secrets \
  -f ./gitops/apps/monitoring/grafana-proxy/values.yaml
```

Notes:

- `secret.name=grafana-auth-secrets` matches bootstrap output from `scripts/bootstrap-runtime-secrets.sh`.
- This chart does not create an IngressRoute. Ensure your external routing forwards the configured proxy path (default `/grafana-proxy`) to this Service.
- This chart also does not serve `/.well-known/jwks.json`. If Grafana is configured with `GF_AUTH_JWT_JWK_SET_URL`, ensure that JWKS URL is provided by another service (for example `gitops/apps/monitoring/grafana-auth`) or adjust Grafana JWT config.

## 4. Deploy frontend

Choose one frontend chart (`web` or `web-frontend`).

Chart differences:

- `gitops/apps/web-frontend`: single IngressRoute template; `ingress.enabled=true` by default.
- `gitops/apps/web`: `ingress.enabled=false` by default; when enabled, two templates render the same IngressRoute name (`<release>-https`).

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

Important API routing note:

- With default frontend runtime config (`runtimeConfig.apiBaseUrl=/api`), the frontend image proxies `/api` to `wearables-bff.wearables-bff.svc.cluster.local:3001` (see `services/web/nginx.conf`).
- If your BFF Service DNS/port differs, set `runtimeConfig.apiBaseUrl` to your externally routed API path/URL or use an image with adjusted nginx config.
