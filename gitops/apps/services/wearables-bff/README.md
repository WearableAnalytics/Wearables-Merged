# Wearables BFF Helm Chart

This chart deploys the `wearables-bff` service and injects runtime config via Kubernetes `ConfigMap` and `Secret`.

## Scope

This README documents Helm/Kubernetes behavior only.

- API behavior and endpoint list: `services/backend/wearables-bff/README.md`
- Frontend runtime config consuming this API: `services/web/readme.md`
- Runtime deploy flow (BFF + other services): `docs/deploy-runtime-config.md`

## Runtime Configuration

Non-sensitive env vars:

- `values.yaml` -> `env.*`
- Rendered by `templates/configmap.yaml`
- Injected through `envFrom.configMapRef` in `templates/deployment.yaml`

Sensitive env vars:

- `values.yaml` -> `secret.*`
- Rendered by `templates/secret.yaml` only when `secret.create=true`
- Injected through `envFrom.secretRef` only when `secret.enabled=true`

Important env detail:

- `env.FRONTEND_ORIGINS` is a comma-separated list used for CORS allow-origins.
- `env.FRONTEND_REDIRECT_URL` is a single URL used for magic-link redirects and approval/login email links.
- `env.BACKEND_URL` is required and used to build magic-link verification URLs.
- Optional token/auth timing and issuer envs are `env.AUTH_SESSION_EXPIRY_SECONDS`, `env.MAGIC_LINK_EXPIRY_SECONDS`, `env.CASE_TOKEN_EXPIRY_SECONDS`, and `env.TOKEN_ISSUER` (defaults are applied by the backend config if omitted).

Important chart behavior:

- `configMap.create=true`: chart creates `<release-name>-config` unless `configMap.name` is set.
- `configMap.create=false`: deployment still references a ConfigMap; you must provide it (typically via `configMap.name`).
- `secret.create=false`: chart expects an existing Secret named `secret.name` (or `<release-name>-secrets` if omitted).
- `secret.enabled=false`: no Secret is mounted into the container.

## Secret Management

Recommended bootstrap command (shared JWT handling for BFF + Grafana proxy):

```bash
./scripts/bootstrap-runtime-secrets.sh
```

Common setup is:

- `secret.enabled: true`
- `secret.create: false`
- `secret.name: "wearables-bff-secrets"`

When using Grafana proxy session-derived identity/case-token compatibility, keep BFF `JWT_SECRET` equal to proxy `APP_JWT_SECRET` (bootstrap script does this automatically).

## Setup Checklist

1. Edit non-sensitive runtime env in `values.yaml` (`env.*`).
2. Ensure a Secret exists with required `JWT_SECRET` and `RESEARCHER_API_ACCESS_TOKEN` (plus `BREVO_API_KEY` when `env.NODE_ENV=production`).
3. Deploy the chart (command below).

If you deploy BFF together with Grafana proxy/frontend, use `docs/deploy-runtime-config.md` for the end-to-end sequence.

## Accessing The Service

Within the cluster:

```text
http://<release-name>.<namespace>.svc.cluster.local:3001
```

Example with release + namespace `wearables-bff`:

```text
http://wearables-bff.wearables-bff.svc.cluster.local:3001
```

Port-forward for local testing:

```bash
kubectl port-forward -n wearables-bff svc/wearables-bff 3001:3001
```

Then call: `http://localhost:3001/api/health`

## Deploy

```bash
helm upgrade --install wearables-bff ./gitops/apps/services/wearables-bff \
  --namespace wearables-bff \
  --create-namespace \
  -f ./gitops/apps/services/wearables-bff/values.yaml
```
