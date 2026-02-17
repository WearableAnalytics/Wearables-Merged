# Wearables BFF Helm Chart

## Runtime configuration

The chart injects environment variables at runtime via:

- `ConfigMap` (non-sensitive values): `templates/configmap.yaml`
- `Secret` (sensitive values): `templates/secret.yaml` when `secret.create=true`, or an existing Secret when `secret.create=false`

Set non-sensitive runtime env under `env` in `values.yaml`.
Set secret name via `secret.name` (defaults to `<release-name>-secrets`).

## Secret management

Recommended (auto bootstrap for BFF + Grafana proxy shared JWT):

```bash
./scripts/bootstrap-runtime-secrets.sh
```

Set `secret.name: "wearables-bff-secrets"` in `values.yaml` (or rely on the release-name default).

## API Endpoints

The service exposes the following mock endpoints:

- `GET    {API_PREFIX}/health`
- `GET    {API_PREFIX}/charite/cases/:cCaseId`
- `GET    {API_PREFIX}/patients`
- `GET    {API_PREFIX}/patients/:patientId`
- `GET    {API_PREFIX}/patients/:patientId/cases`
- `GET    {API_PREFIX}/cases`
- `GET    {API_PREFIX}/cases/:caseId`
- `POST   {API_PREFIX}/cases/from-charite-case`
- `POST   {API_PREFIX}/cases/verify-token`

## Accessing the Service

### Within the Cluster

Other services can access the BFF using:

```
http://wearables-bff.wearables-bff.svc.cluster.local:3001
```

### Port Forwarding (Development)

For local development and testing:

```bash
kubectl port-forward -n wearables-bff \
  svc/wearables-bff 3001:3001
```

Then access the service at `http://localhost:3001/api/health`

## Deploy

helm upgrade --install wearables-bff ./gitops/apps/services/wearables-bff \
  --namespace wearables-bff --create-namespace
