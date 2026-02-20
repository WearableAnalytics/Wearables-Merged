# Web Frontend Helm Chart

Helm chart for deploying the `web` frontend service.

## Scope

This README documents chart behavior only.

- Frontend runtime/source behavior: `services/web/README.md`
- BFF chart/runtime config: `gitops/apps/services/wearables-bff/README.md`
- Grafana proxy chart setup: `gitops/apps/monitoring/grafana-proxy/README.md`
- Shared runtime deploy flow: `docs/deploy-runtime-config.md`

## Chart Selection

- Use this chart as the default frontend GitOps chart when deploying ingress.
- This chart has a single IngressRoute template and avoids duplicate resource naming.

## Runtime Config Injection

This chart writes and mounts `/usr/share/nginx/html/runtime-config.js`:

- ConfigMap template: `templates/runtime-configmap.yaml`
- Deployment mount: `templates/deployment.yaml`

Values mapping:

- `runtimeConfig.apiBaseUrl` -> `window.__APP_CONFIG__.API_BASE_URL`
- `runtimeConfig.grafanaProxyUrl` -> `window.__APP_CONFIG__.GRAFANA_PROXY_URL`
- `runtimeConfig.socketUrl` -> `window.__APP_CONFIG__.SOCKET_URL`

## Important Chart Behavior

- `runtimeConfigMap.create=true`: chart creates `<release-name>-runtime-config` unless `runtimeConfigMap.name` is set.
- `runtimeConfigMap.create=false`: deployment still mounts a ConfigMap; you must provide it (usually via `runtimeConfigMap.name`).
- `replicaCount` is used by the deployment template.
- `runtimeConfig.grafanaProxyUrl` must match Grafana proxy path (`gitops/apps/monitoring/grafana-proxy/values.yaml` -> `proxy.prefix`) and your external route path.
- Service is `ClusterIP` on `service.port` (default `80`) forwarding to `service.targetPort` (default `80`).
- Ingress is optional and controlled by `ingress.enabled`.
- Ingress defaults to enabled and renders one `websecure` route with `Host(...) && PathPrefix(...)`.
- No Secret object is managed by this chart for runtime config (frontend config is public by design).

## API Routing Dependency

- Default frontend runtime config is `runtimeConfig.apiBaseUrl=/api`.
- In the default frontend image, nginx proxies `/api` to `wearables-bff.wearables-bff.svc.cluster.local:3001` (`services/web/nginx.conf`).
- If your BFF DNS/namespace/port is different, either set `runtimeConfig.apiBaseUrl` to your externally routed API URL/path or use an image with adjusted nginx upstream config.

## Deploy

```bash
helm upgrade --install web ./gitops/apps/web-frontend \
  -n web \
  --create-namespace \
  -f ./gitops/apps/web-frontend/values.yaml
```
