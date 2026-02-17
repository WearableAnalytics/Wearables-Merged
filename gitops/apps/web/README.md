# Wearables Web Frontend Helm Chart

This Helm chart deploys the Vite + React web frontend for the Wearables Analytics platform.

## Service Details

This chart injects frontend runtime config via a mounted `runtime-config.js` ConfigMap.
You can reuse the same image across environments and only change Helm values.

## Installation

### Basic Installation

Deploy the web frontend to your cluster:

```bash
helm upgrade --install wearables-web ./gitops/apps/web \
  --values ./gitops/apps/web/values.yaml \
  --namespace web \
  --create-namespace
```

## Configuration

### Runtime frontend configuration

The chart writes these runtime values into `window.__APP_CONFIG__`:

- **`apiBaseUrl`**: API endpoint for backend communication (default `/api`)
- **`grafanaProxyUrl`**: Path to Grafana proxy (default `/grafana-proxy`)
- **`socketUrl`**: Optional Socket.IO endpoint

### Example values

```yaml
runtimeConfig:
  apiBaseUrl: "/api"
  grafanaProxyUrl: "/grafana-proxy"
  socketUrl: ""
```

## Accessing the Frontend
To access the frontend from your machine, first set up port-forwarding from the jumphost
to your local machine.

**Important**: You need to setup TWO port-forwards: 8080->8080 and 3001->3001

Then log in to the jumphost and run:

```bash
kubectl port-forward -n web svc/wearables-web 8080:80
```

Now open the frontend in your browser:

```
http://localhost:8080
```

After you enter your email it will say that approval is pending. Please contact me or
anyone who already has access to approve your account.
