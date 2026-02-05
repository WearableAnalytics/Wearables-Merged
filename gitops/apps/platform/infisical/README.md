# Infisical Secret Vault

Helm chart for deploying Infisical secret managment platform with MongoDB and Redis.

## Components

- **Infisical** - secret vault
- **MongoDB** - backend database
- **Redis** - cache (runs in-memory, no PVC needed)

## Requirements

- Any Kubernetes cluster (K3s, EKS, GKE, AKS, minikube, etc.)
- Helm 3.x
- cert-manager (optional, for HTTPS)
- Ingress controller (Traefik, nginx, or any other)

## Setup

### 1. Generate secrets

Before deploying, change the default secrets in `values.yaml`:

```bash
# Generate encryption key (32 chars)
openssl rand -hex 16

# Generate JWT secrets
openssl rand -base64 32
```

Edit `values.yaml` with your generated keys:
```yaml
mongodb:
  auth:
    username: your-user
    password: your-secure-password

infisical:
  encryptionKey: "your-32-char-key"
  jwtAuthSecret: "your-jwt-secret"
  jwtRefreshSecret: "your-refresh-secret"
  jwtServiceSecret: "your-service-secret"
```

### 2. Install

```bash
# Basic instalation
helm install infisical ./gitops/apps/platform/infisical -n platform --create-namespace

# With ingress enabled
helm install infisical ./gitops/apps/platform/infisical -n platform \
  --set ingress.enabled=true
```

### 3. Check status

```bash
kubectl get pods -l app=infisical -n platform
kubectl logs -l app=infisical -f -n platform
```

## Acess

Inside cluster: `http://infisical:8080`

External (with ingress): `https://infisical.wearable-analytics.de`

## Post-Install

1. Open Infisical UI in browser
2. Create admin acccount
3. Setup organization & projects
4. Add secrets to your projects
5. Generate service tokens for apps

## Integration Example

You can use Infisical to manage secrets for other services like PostgreSQL instead of hardcoding them in helm charts.

## Uninstall

```bash
helm uninstall infisical -n platform

# Delete PVC manually if needed
kubectl delete pvc infisical-mongodb-pvc -n platform
```

## Notes

- Change all default passwords before production!
- Keep encryption key safe - without it you cant recover secrets
- Redis runs without PVC to save storage in managed cluster
- Only MongoDB uses PVC (10Gi)
- Default storageClass is `local-path` (K3s default). For other clusters change in values.yaml.
