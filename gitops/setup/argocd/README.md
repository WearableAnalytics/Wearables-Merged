# GitOps Deployment with ArgoCD

Declarative GitOps configuration using App-of-Apps pattern for the Wearables Platform on Kubernetes.

ArgoCD monitors the `main` branch and automatically synchronizes Helm charts in `gitops/apps/` to the cluster

## Quick Start

### 1. Install ArgoCD
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 2. Deploy Root Application
```bash
kubectl apply -f gitops/setup/argocd/root-app.yaml
```

### 3. Access Web UI
```bash
# Port-forward to ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Retrieve initial admin password:
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
```
Open `https://localhost:8080` (Username: `admin`).

## Managed Applications (`gitops/setup/argocd/apps/`)
* `cloud-connector`: Multi-Provider Cloud Ingestion & Webhooks (Garmin etc.)
* `importservice`: Mobile Ingestion Endpoint
* `wearables-bff`: Backend-for-Frontend & Auth
* `mapper-validator`: FHIR Mapping & Validation
* `web-frontend`: Clinical Web UI
