# Wearables Web Frontend Helm Chart

## Runtime configuration

This chart mounts a runtime `runtime-config.js` file from a Kubernetes `ConfigMap`.
The Docker image stays environment-agnostic and runtime URLs are injected in-cluster.

Configured values in `values.yaml`:

- `runtimeConfig.apiBaseUrl` (default `/api`)
- `runtimeConfig.grafanaProxyUrl` (default `/grafana-proxy`)
- `runtimeConfig.socketUrl` (optional)

## Deploy

```bash
helm upgrade --install web-frontend ./gitops/apps/web-frontend \
  -n web-frontend --create-namespace \
  -f ./gitops/apps/web-frontend/values.yaml
```

## Notes

- No sensitive values should be put into frontend runtime config.
- Frontend config is public in the browser by design.
