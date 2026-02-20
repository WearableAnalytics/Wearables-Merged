# Wearables Web Helm Chart

Helm chart for deploying the `wearables-web` frontend.

## Scope

This README documents chart behavior only.

- Frontend runtime/source behavior: `services/web/readme.md`
- BFF chart/runtime config: `gitops/apps/services/wearables-bff/README.md`
- Grafana proxy chart setup: `gitops/apps/monitoring/grafana-proxy/README.md`
- Shared runtime deploy flow: `docs/deploy-runtime-config.md`

## Chart Status

- This chart is still usable for runtime-config mounting and Service deployment.
- If you need Ingress, prefer `gitops/apps/web-frontend` until the duplicate IngressRoute template naming in this chart is resolved.

## Runtime Config Injection

This chart mounts `runtime-config.js` into the nginx web root:

- File path in container: `/usr/share/nginx/html/runtime-config.js`
- Source template: `templates/runtime-configmap.yaml`
- Mounted by: `templates/deployment.yaml`

Values mapping:

- `runtimeConfig.apiBaseUrl` -> `window.__APP_CONFIG__.API_BASE_URL`
- `runtimeConfig.grafanaProxyUrl` -> `window.__APP_CONFIG__.GRAFANA_PROXY_URL`
- `runtimeConfig.socketUrl` -> `window.__APP_CONFIG__.SOCKET_URL`

## Important Chart Behavior

- `runtimeConfigMap.create=true`: chart creates `<release-name>-runtime-config` unless `runtimeConfigMap.name` is set.
- `runtimeConfigMap.create=false`: deployment still mounts a ConfigMap; you must provide it (usually via `runtimeConfigMap.name`).
- `replicaCount` is used by the deployment template.
- `runtimeConfig.grafanaProxyUrl` must match Grafana proxy path (`gitops/apps/monitoring/grafana-proxy/values.yaml` -> `proxy.prefix`) and your external route path.
- No Secret object is managed by this chart for runtime config (frontend config is public by design).

Ingress notes:

- Ingress rendering is gated by `ingress.enabled`.
- This chart currently has two IngressRoute templates (`ingressroute.yaml` and `ingressroute-secure.yaml`) with the same resource name when enabled.

API routing dependency:

- Default frontend runtime config is `runtimeConfig.apiBaseUrl=/api`.
- In the default frontend image, nginx proxies `/api` to `wearables-bff.wearables-bff.svc.cluster.local:3001` (`services/web/nginx.conf`).
- If your BFF DNS/namespace/port is different, either set `runtimeConfig.apiBaseUrl` to your externally routed API URL/path or use an image with adjusted nginx upstream config.

## Deploy

```bash
helm upgrade --install wearables-web ./gitops/apps/web \
  --namespace web \
  --create-namespace \
  -f ./gitops/apps/web/values.yaml
```

## Default Values

`values.yaml` defaults:

- service: `ClusterIP` on port `80`
- runtime config:
  - `apiBaseUrl: "/api"`
  - `grafanaProxyUrl: "/grafana-proxy"`
  - `socketUrl: ""`
