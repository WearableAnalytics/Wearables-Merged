# Wearables Web Frontend Helm Chart

This Helm chart deploys the Vite + React web frontend for the Wearables Analytics platform.

## Overview

The wearables-web is a modern React SPA built with Vite, TypeScript, and Tailwind CSS. It provides the user interface for patient and case management, displaying health analytics and Grafana dashboards.

## Service Details

- **Application**: Wearables Web Frontend (Vite + React)
- **Port**: 80 (nginx)
- **Service Type**: ClusterIP
- **Image Repository**: gmsdaniil/wearables-web

## Prerequisites

- Kubernetes cluster (1.19+)
- Helm 3.x
- kubectl configured to access your cluster
- Backend API service (registration-service-node or registration-service) running

## Architecture

The application is built in two stages:
1. **Build Stage**: Node.js compiles the Vite/React app with build-time environment variables
2. **Runtime Stage**: Nginx serves the static assets

**Important**: Environment variables like `VITE_API_BASE_URL` are **baked into the build** and cannot be changed at runtime without rebuilding the image.

## Installation

### Basic Installation

Deploy the web frontend to your cluster:

```bash
helm upgrade --install wearables-web ./wearables-web \
  --values ./wearables-web/values.yaml \
  --namespace wearables-web \
  --create-namespace
```

### Custom Configuration

Override default values during installation:

```bash
helm upgrade --install wearables-web ./wearables-web \
  --values ./wearables-web/values.yaml \
  --namespace wearables-web \
  --create-namespace \
  --set image.tag=0.1.0 \
  --set replicaCount=2
```

## Configuration

### Key Configuration Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Docker image repository | `gmsdaniil/wearables-web` |
| `image.tag` | Image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `Always` |
| `service.type` | Kubernetes service type | `ClusterIP` |
| `service.port` | Service port (nginx) | `80` |
| `buildArgs.VITE_API_BASE_URL` | API endpoint (build-time) | `"/api"` |
| `buildArgs.VITE_BACKEND_URL` | Backend URL (build-time) | `""` |
| `buildArgs.VITE_GRAFANA_IFRAME_URL` | Grafana iframe URL | `"/grafana/"` |

### Build-Time Environment Variables

The frontend uses Vite environment variables that must be set during the Docker build:

- **`VITE_API_BASE_URL`**: API endpoint for backend communication
  - Relative path: `/api` (routed via Ingress)
  - Absolute URL: `http://backend.example.com/api`
- **`VITE_BACKEND_URL`**: Optional backend base URL
- **`VITE_GRAFANA_IFRAME_URL`**: Path to Grafana iframe (default: `/grafana/`)

### Rebuilding with Custom Environment Variables

To change API endpoints, rebuild the Docker image:

```bash
cd services/web

docker build -f ../../services/web/Dockerfile \
  -t gmsdaniil/wearables-web:custom \
  --build-arg VITE_API_BASE_URL="https://api.example.com" \
  --build-arg VITE_GRAFANA_IFRAME_URL="/grafana/" \
  ../..

docker push gmsdaniil/wearables-web:custom
```

Then update the Helm chart to use the new tag:

```bash
helm upgrade wearables-web ./wearables-web \
  --set image.tag=custom \
  --namespace wearables-web
```

## Accessing the Frontend

### Within the Cluster

Other services can access the frontend using:

```
http://wearables-web.wearables-web.svc.cluster.local:80
```

### Port Forwarding (Development)

For local development and testing:

```bash
kubectl port-forward -n wearables-web svc/wearables-web 8080:80
```

Then access the frontend at `http://localhost:8080`

### Via Ingress (Production)

For production access, configure an Ingress resource or IngressRoute (if using Traefik):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: wearables-web-ingress
  namespace: wearables-web
spec:
  rules:
  - host: wearable-analytics.de
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: wearables-web
            port:
              number: 80
```

## API Routing

The frontend expects the backend API at the path configured in `VITE_API_BASE_URL`. Common setups:

### Option 1: Ingress with Path Routing

Frontend: `https://wearable-analytics.de/` → wearables-web service
Backend: `https://wearable-analytics.de/api` → registration-service-node

Set `VITE_API_BASE_URL="/api"` during build.

### Option 2: Separate Subdomains

Frontend: `https://app.example.com/` → wearables-web
Backend: `https://api.example.com/api` → registration-service-node

Set `VITE_API_BASE_URL="https://api.example.com/api"` during build.

## Health Checks

The deployment includes liveness and readiness probes:

- **Liveness Probe**: Checks if nginx is responsive (`GET /`)
- **Readiness Probe**: Checks if the app is ready to serve traffic (`GET /`)

## Uninstalling

To remove the deployment:

```bash
helm uninstall wearables-web --namespace wearables-web
```

To also delete the namespace:

```bash
kubectl delete namespace wearables-web
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n wearables-web
```

### View Logs

```bash
kubectl logs -n wearables-web -l app=wearables-web
```

### Describe Pod for Events

```bash
kubectl describe pod -n wearables-web -l app=wearables-web
```

### Test Service Connectivity

```bash
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n wearables-web -- \
  curl http://wearables-web:80
```

### Check Nginx Configuration

```bash
kubectl exec -it -n wearables-web deployment/wearables-web -- cat /etc/nginx/conf.d/default.conf
```

### API Connection Issues

If the frontend can't connect to the API:

1. Check `VITE_API_BASE_URL` was set correctly during build
2. Verify backend service is running and accessible
3. Check Ingress routing configuration
4. Look at browser console for CORS or network errors

## Development Workflow

### Local Development

For local development, run the Vite dev server directly:

```bash
cd services/web
npm install
npm run dev
```

Set environment variables in `.env`:

```env
VITE_API_BASE_URL=http://localhost:3001/api
VITE_GRAFANA_IFRAME_URL=/grafana/
```

### Building for Production

Build and push a new image:

```bash
# From repo root
docker build -f services/web/Dockerfile \
  -t gmsdaniil/wearables-web:0.1.0 \
  --build-arg VITE_API_BASE_URL="/api" \
  .

docker push gmsdaniil/wearables-web:0.1.0
```

Deploy the new version:

```bash
helm upgrade wearables-web ./wearables-web \
  --set image.tag=0.1.0 \
  --namespace wearables-web
```

## Dependencies

The frontend requires:

- **Backend API**: registration-service-node or registration-service
- **Grafana** (optional): For embedded analytics dashboards

## TODO

- Configure resource requests/limits
- Add HorizontalPodAutoscaler for scaling
- Set up Ingress/IngressRoute for external access
- Implement ConfigMap for runtime configuration (if needed)
- Add monitoring and alerting integration

## Related Documentation

- Main GitOps README: [../README.md](../README.md)
- Application Source: [../../services/web](../../services/web)
- Backend Service: [../services/registration-service-node](../services/registration-service-node)
- API Schema: [../../services/packages/api-schema](../../services/packages/api-schema)
