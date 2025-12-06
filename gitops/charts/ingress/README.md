# Ingress Helm Chart

This Helm chart deploys an NGINX ingress with HTTPS support using Let's Encrypt certificates for the wearables application.

## What We've Set Up

This ingress configuration provides:
- ✅ NGINX Ingress Controller for routing external traffic
- ✅ Automatic HTTPS with Let's Encrypt certificates
- ✅ Domain-based routing to `wearables.cherep.co`
- ✅ Path-based routing with regex support
- ✅ Automatic HTTP to HTTPS redirect

## Complete Setup Steps (Already Completed)

### Step 1: Install NGINX Ingress Controller
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml
```

### Step 2: Install cert-manager for Automatic SSL
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

### Step 3: Create Let's Encrypt ClusterIssuer
```bash
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@cherep.co
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### Step 4: Deploy Ingress Chart
```bash
helm upgrade --install ingress ./charts/ingress \
  --values ./charts/ingress/values.yaml \
  --namespace importservice --create-namespace
```

## Current Configuration

- **Domain**: `wearables.cherep.co`
- **Backend Service**: `importservice:8000` 
- **Path Routing**: `/import/(.*)` → forwards to service
- **TLS**: Automatic Let's Encrypt certificate
- **Namespace**: `importservice` (same as the backend service)

## How It Works

### URL Routing
- `https://wearables.cherep.co/import/health` → `importservice:8000/health`
- `https://wearables.cherep.co/import/data` → `importservice:8000/data`
- `https://wearables.cherep.co/import/` → `importservice:8000/`

### Certificate Management
1. cert-manager detects the ingress with TLS annotations
2. Creates a Certificate resource automatically
3. Challenges domain ownership via HTTP-01 validation
4. Stores the issued certificate in `wearables-tls` secret

## Adding More Services

To route additional services, update `values.yaml`:

```yaml
services:
  importservice:
    name: importservice
    port: 8000
    path: /import/(.*)
    pathType: ImplementationSpecific
  
  another-service:
    name: another-service  
    port: 3000
    path: /api/(.*)
    pathType: ImplementationSpecific
```

## Useful Commands

```bash
# Check ingress status
kubectl get ingress -n importservice

# Check certificate status  
kubectl get certificate -n importservice

# Check TLS secret
kubectl get secret wearables-tls -n importservice

# View certificate details
kubectl describe certificate wearables-tls -n importservice
```