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

The root application does not manage itself: after a change to `root-app.yaml`, apply it again with the same command.

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
* `argocd-image-updater`: Updates the images built by `publish-images.yml` (production only, see below)
* `sealed-secrets`: Sealed Secrets controller in `kube-system` (production only, `prune: false`). It decrypts the SealedSecrets of the runtime secrets with the cluster's single key (`keyrenewperiod: "0"`, no automatic key renewal)

`gitops/setup/argocd/apps/` is a small Helm chart: `templates/applications.yaml` creates one Argo CD application per entry in `values.yaml`. To add or remove an application, edit the `apps` list there. Entries with `productionOnly: true` are skipped by `values-local.yaml` (`production: false`).

## Image Updates (Argo CD Image Updater)

`gitops/apps/platform/argocd-image-updater/` installs the [Argo CD Image Updater](https://argocd-image-updater.readthedocs.io/) into the `argocd` namespace, only in production. It checks GHCR every 2 minutes for the images that `.github/workflows/publish-images.yml` builds and deploys the newest version.

* **Which tag:** strategy `semver` without a version constraint, so the highest `X.Y.Z` tag, including major updates. `allowTags` only accepts plain `X.Y.Z`, so the `-stage` tags, the commit SHA tags and `latest` are never deployed.
* **Which images:** the `images` list in `values.yaml` of the chart (Argo CD application name and image). To add a service, add an entry there; its chart must read the image from `image.repository` and `image.tag`.
* **How it is written:** write-back method `argocd`. The updater sets `image.repository` and `image.tag` as Helm parameters in the application; git keeps `tag: latest` as the fallback. The deployed version is therefore only visible in the cluster, not in git.
* **Root application:** `root-app.yaml` ignores `/spec/source/helm/parameters` of the child applications (`ignoreDifferences` with `RespectIgnoreDifferences=true`). Without it, selfHeal of the root application would reset the parameters to git and the updater would set them again in a loop. Apply `root-app.yaml` before the image updater reaches `main` (see Quick Start, step 2).
* **Same tag, new image:** a rebuild that overwrites an existing version tag is not detected, because the version does not change.

Check the status and the deployed versions:

```bash
kubectl get imageupdaters -n argocd
kubectl logs -n argocd deploy/argocd-image-updater-controller --tail=100
kubectl get application wearables-bff -n argocd -o jsonpath='{.spec.source.helm.parameters}'; echo
```

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

The local minikube cluster uses the same chart with `values-local.yaml` (see `gitops/local/README.md`, step 16), so both setups deploy the same applications. Check what the chart renders with:

```bash
helm template apps gitops/setup/argocd/apps                                  # production
helm template apps gitops/setup/argocd/apps -f gitops/setup/argocd/apps/values-local.yaml   # local
```
