# Wearables Web Frontend Helm Chart

This Helm chart deploys the Vite + React web frontend for the Wearables Analytics platform.

## Service Details

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

## Configuration

### Build-Time Environment Variables

The frontend uses Vite environment variables that must be set during the Docker build:

- **`VITE_API_BASE_URL`**: API endpoint for backend communication
  - Relative path: `/api` (routed via Ingress)
  - Absolute URL: `http://backend.example.com/api`
- **`VITE_BACKEND_URL`**: Optional backend base URL
- **`VITE_GRAFANA_PROXY_URL`**: Path to Grafana proxy (default: `/grafana/`)

### Rebuilding with Custom Environment Variables

To change API endpoints, rebuild the Docker image:

```bash
cd services/web

docker build -f ../../services/web/Dockerfile \
  -t gmsdaniil/wearables-web:custom \
  --build-arg VITE_API_BASE_URL="https://api.example.com" \
  --build-arg VITE_GRAFANA_PROXY_URL="/grafana/" \
  ../..

docker push gmsdaniil/wearables-web:custom
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
