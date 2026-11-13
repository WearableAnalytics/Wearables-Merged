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
* `web-frontend`: Clinical Web UI (Helm release `web`, as in `setup-script.sh`)

`gitops/setup/argocd/apps/` is a small Helm chart: `templates/applications.yaml` creates one Argo CD application per entry in `values.yaml`. To add or remove an application, edit the `apps` list there.

## Secrets

The charts do not create secrets with real values; they reference secrets that exist before the sync. `scripts/bootstrap-runtime-secrets.sh` creates `prod-postgres-secret`, `db-lord-secrets`, `wearables-bff-secrets` and `grafana-auth-secrets` (see `gitops/setup/README.md`).

**Postgres admin password:** Postgres only reads `POSTGRES_PASSWORD` on its first start; afterwards the password is stored in the database. Before setting `PROD_POSTGRES_PASSWORD`, read the current value and check that it is valid:

```bash
kubectl get secret prod-postgres-secret -n prod-postgres -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d; echo
kubectl run pg-check --rm -it --restart=Never -n prod-postgres --image=postgres:18-alpine \
  --env=PGPASSWORD='<password>' -- psql -h prod-postgres -U postgres -c 'select 1'
```

If it is not valid (or it is the value that used to be in `values.yaml`, which is public in the git history), set a new one in the database and use that:

```bash
kubectl exec -n prod-postgres prod-postgres-0 -- psql -U postgres -c "ALTER USER postgres PASSWORD '<new password>'"
```

**One-time migration of `wearables-bff-secrets`:** until the change to `secret.create: false`, Argo CD rendered this secret from the chart (with `JWT_SECRET: dev-secret`) and tracks it. Once the change is on `main`, prune would delete it. As long as `main` still renders the secret, Argo CD reverts any change to it, so the migration has two parts:

1. Before the change reaches `main`, protect the secret from prune (Argo CD keeps annotations it does not set itself):

   ```bash
   kubectl annotate secret wearables-bff-secrets -n wearables-bff argocd.argoproj.io/sync-options=Prune=false
   ```

2. After the merge, once the `wearables-bff` application has synced the new revision, detach the secret from Argo CD and remove the protection again:

   ```bash
   kubectl annotate secret wearables-bff-secrets -n wearables-bff argocd.argoproj.io/tracking-id- argocd.argoproj.io/sync-options-
   kubectl label secret wearables-bff-secrets -n wearables-bff app.kubernetes.io/instance-
   ```

Then check its `JWT_SECRET`. If it is `dev-secret`, replace it with a random one for the BFF and the Grafana proxy, set `JWT_SECRET` in `importservice-secrets` to the same value, and restart the three deployments. This logs out all users and invalidates issued case tokens. Only do it after step 2, otherwise Argo CD writes `dev-secret` back.

```bash
kubectl get secret wearables-bff-secrets -n wearables-bff -o jsonpath='{.data.JWT_SECRET}' | base64 -d; echo
ROTATE_SHARED_APP_JWT_SECRET=true ./scripts/bootstrap-runtime-secrets.sh
```

The local minikube cluster uses the same chart with `values-local.yaml` (see `gitops/local/README.md`, step 16), so both setups deploy the same applications. Check what the chart renders with:

```bash
helm template apps gitops/setup/argocd/apps                                  # production
helm template apps gitops/setup/argocd/apps -f gitops/setup/argocd/apps/values-local.yaml   # local
```
