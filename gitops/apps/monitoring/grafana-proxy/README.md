# Grafana Proxy Helm Chart

## Runtime configuration

The chart injects runtime configuration through:

- `ConfigMap` (`templates/configmap.yaml`) for non-sensitive env vars
- `Secret` (`templates/secret.yaml`) for sensitive values (or an existing Secret)

By default, `secret.create=false`, so you should create the Secret externally.

## Secret management

Recommended (auto bootstrap for BFF + Grafana proxy shared JWT):

```bash
./scripts/bootstrap-runtime-secrets.sh
```

Then set `secret.name: "grafana-auth-secrets"` in `values.yaml` (or use matching release-name defaults).

## Deploy

```bash
helm upgrade --install grafana-auth ./gitops/apps/monitoring/grafana-proxy \
  -n monitoring --create-namespace \
  -f ./gitops/apps/monitoring/grafana-proxy/values.yaml
```
