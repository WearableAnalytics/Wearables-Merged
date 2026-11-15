# Wearables BFF Helm Chart

This chart deploys the `wearables-bff` service and injects runtime config via Kubernetes `ConfigMap` and `Secret`.

## Scope

This README documents Helm/Kubernetes behavior only.

- API behavior and endpoint list: `services/backend/wearables-bff/README.md`
- Frontend runtime config consuming this API: `services/web/README.md`
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
- Token/auth timing and issuer envs are required: `env.AUTH_SESSION_EXPIRY_SECONDS`, `env.MAGIC_LINK_EXPIRY_SECONDS`, `env.CASE_TOKEN_EXPIRY_SECONDS`, and `env.TOKEN_ISSUER`.

Important chart behavior:

- `configMap.create=true`: chart creates `<release-name>-config` unless `configMap.name` is set.
- `configMap.create=false`: deployment still references a ConfigMap; you must provide it (typically via `configMap.name`).
- `secret.create=false`: chart expects an existing Secret named `secret.name` (or `<release-name>-secrets` if omitted).
- `secret.enabled=false`: no Secret is mounted into the container.

## Secret Management

Secrets are managed by the cluster operators. The legacy bootstrap script only
handles the older JWT/email inputs; it does not provision all account-authority
credentials required by this branch. No bootstrap or cluster command is run by
this PR. See `docs/ingestion-deployment.md` for the complete operator handoff.

The chart defaults (`values.yaml`) expect this existing secret; Argo CD deploys the chart with them:

- `secret.enabled: true`
- `secret.create: false`
- `secret.name: "wearables-bff-secrets"`

This is also the chart default. It creates no Secret or placeholder credential.
The existing Secret must supply distinct `JWT_SECRET`, `CONTROL_WRITE_TOKEN`,
`API_TOKEN_SERVICE_TOKEN` and `DATABASE_OPERATOR_TOKEN`. Match the corresponding
database credentials; `DATABASE_OPERATOR_TOKEN` maps to `LEGACY_OPERATOR_TOKEN`.
`BREVO_API_KEY` may be missing or `disabled`. This keeps the service running but
new email-login requests return 503. No usable links are written to logs.
Real email delivery requires the provider key and sender configuration, then a
controlled restart. Existing sessions remain subject to current authority.

Before account cutover, override the legacy `env.DATABASE_API_URL` with the
actual private HTTPS authority endpoint and its valid TLS trust. The application
rejects the old plaintext address. This PR does not guess or provision that
endpoint. Keep `COOKIE_SECURE=true`; production cannot use the development bypass.

When using Grafana proxy session-derived identity/case-token compatibility:

- keep BFF `JWT_SECRET` equal to proxy `APP_JWT_SECRET` (bootstrap script does this automatically)
- keep BFF `env.TOKEN_ISSUER` equal to proxy `session.jwtIssuer` / runtime `APP_JWT_ISSUER` (default `wearables-bff`)

## Setup Checklist

1. Edit non-sensitive runtime env in `values.yaml` (`env.*`).
2. Ensure `values.yaml` explicitly sets required runtime envs (`FRONTEND_ORIGINS`, `FRONTEND_REDIRECT_URL`, `BACKEND_URL`, `AUTH_SESSION_EXPIRY_SECONDS`, `MAGIC_LINK_EXPIRY_SECONDS`, `CASE_TOKEN_EXPIRY_SECONDS`, `TOKEN_ISSUER`).
3. Have the operators provision all credentials listed above and the private HTTPS database-authority endpoint.
4. Coordinate images, migrations and auto-sync before deployment. Email can stay disabled; new login then remains unavailable.

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
