# Local Minikube setup

Runs the platform's Helm charts on a single-node Minikube cluster on a developer machine. Each chart keeps its production defaults in `values.yaml`; a `values-local.yaml` next to it holds only the local differences (fewer replicas, smaller resources, Minikube storage).

Everything the production setup script installs runs locally, except cert-manager (no TLS locally) and the ML pipeline. Locally it needs about 2 CPUs and 3.5 GiB of the cluster's memory.

## Quick start

```bash
minikube start --driver=docker --cpus=4 --memory=8g --disk-size=40g
./gitops/local/setup-local.sh     # builds the images, installs everything (~10 min the first time)
minikube tunnel                   # in a second terminal, keep it open
```

Then open http://wearables.localhost and log in with `admin@example.com`.

`setup-local.sh` runs the steps below in order and can be run again at any time: Helm upgrades the releases, and secrets are only created when they are missing. Use `--skip-build` to keep the current images. Every `kubectl` and `helm` call in the script is pinned to the `minikube` context. The sections below explain each step and how to check it.

With `--argocd`, Argo CD deploys five of the services from GitHub instead of Helm, as in production (step 16).

## Prerequisites

| Tool | Tested version |
|---|---|
| Docker Desktop (or another Docker engine) | 29.x, with at least 4 CPUs and 10 GB memory |
| minikube | 1.38.1 |
| kubectl | 1.36 |
| Helm | 4.1 |

Tested on an Apple Silicon MacBook with 16 GB RAM.

## 1. Start the cluster

```bash
minikube start --driver=docker --cpus=4 --memory=8g --disk-size=40g
kubectl config current-context   # must print: minikube
```

Every following command runs against the current kubectl context. Check that it is `minikube` before running anything, so nothing is applied to another cluster by mistake.

## 2. Build the service images

```bash
./gitops/local/build-local-images.sh                 # all services
./gitops/local/build-local-images.sh wearables-bff   # only the named ones
```

The script builds each service straight into Minikube as `wearables-local/<service>:dev`. Minikube builds natively, so the images match the machine: arm64 on Apple Silicon, amd64 on x86. No registry or image archive is involved.

## 3. Kafka

Kafka is managed by the Strimzi operator. The chart uses Kafka 4.1.0 and the `kafka.strimzi.io/v1` API, which only Strimzi 0.49.0 to 1.0.0 support, so the operator version is pinned:

```bash
helm install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator \
  --version 1.0.0 --namespace kafka --create-namespace

helm upgrade --install kafka gitops/apps/platform/kafka \
  -f gitops/apps/platform/kafka/values.yaml \
  -f gitops/apps/platform/kafka/values-local.yaml \
  --namespace kafka
```

Locally Kafka runs one broker (production: three) with 250m CPU / 1 Gi memory requested, and every topic has one replica. Partition counts stay as in production, because the mapper expects 30 partitions on `wearables-raw`.

Check that the broker and the topics are ready (takes about a minute):

```bash
kubectl wait -n kafka kafka/kafka --for=condition=Ready --timeout=480s
kubectl get pods -n kafka
kubectl get kafkatopics -n kafka   # dlq, wearables-lp, wearables-raw: READY True
```

The `kafka-mosquitto-source` KafkaConnector stays without status: the chart has no Kafka Connect cluster for it to run on. It is harmless locally.

## 4. FHIR mapper

Needs Kafka from step 3 and the image from step 2 (`./gitops/local/build-local-images.sh mapper-validator`).

```bash
helm upgrade --install mapper-validator gitops/apps/services/mapper-validator \
  -f gitops/apps/services/mapper-validator/values.yaml \
  -f gitops/apps/services/mapper-validator/values-local.yaml \
  --namespace kafka
```

Locally the mapper runs one instance (production: three) with three stream threads and a 1 Gi memory limit. `PARTITIONS` stays at 30, matching `wearables-raw`. The Java heap is capped at 768 MiB through `JAVA_TOOL_OPTIONS`; without it the image keeps its default of `-Xmx3500m`, which would exceed the local memory limit.

Check that the mapper is connected:

```bash
kubectl rollout status deployment/mapper-validator -n kafka
kubectl logs -n kafka deployment/mapper-validator | grep 'Picked up'           # -Xmx768m
kubectl logs -n kafka deployment/mapper-validator | grep 'REBALANCING to RUNNING'
```

After rebuilding the image, restart the pod so it picks up the new image:

```bash
kubectl rollout restart deployment/mapper-validator -n kafka
```

## 5. InfluxDB and Telegraf

Telegraf reads the mapped readings from the `wearables-lp` topic and writes them to InfluxDB.

```bash
helm upgrade --install influxdb gitops/apps/monitoring/influxdb \
  -f gitops/apps/monitoring/influxdb/values.yaml \
  -f gitops/apps/monitoring/influxdb/values-local.yaml \
  --namespace influx --create-namespace

helm upgrade --install telegraf gitops/apps/monitoring/telegraf \
  -f gitops/apps/monitoring/telegraf/values.yaml \
  -f gitops/apps/monitoring/telegraf/values-local.yaml \
  --namespace telegraf --create-namespace
```

Locally InfluxDB sets itself up on its first start (`initSetup` in `values-local.yaml`), so there is no manual token step. The local credentials match the Docker Compose stack:

| Setting | Value |
|---|---|
| User / password | `admin` / `admin-password` |
| Org | `wearables-project` |
| Bucket | `measurements` |
| Token | `dev-influx-token` |

The setup only runs on an empty volume. After changing these values, delete the release and its volume (`helm uninstall influxdb -n influx && kubectl delete pvc influxdb-pvc -n influx`) and install again. Telegraf runs one replica (production: three) and uses the same org, bucket and token.

Check the pipeline from Kafka to InfluxDB with one test line:

```bash
echo "local_pipeline_check,device-id=local-test value=1 $(date +%s)000000000" | \
  kubectl exec -i -n kafka kafka-dual-role-0 -- \
  bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic wearables-lp

kubectl exec -n influx deployment/influxdb-deployment -- influx query \
  --org wearables-project --token dev-influx-token \
  'from(bucket:"measurements") |> range(start:-10m) |> filter(fn:(r)=> r._measurement=="local_pipeline_check")'
```

The query returns the `value` field and a `t_ingested` field that Telegraf adds.

To open the InfluxDB UI: `kubectl port-forward -n influx svc/influxdb-service 8086:8086`, then http://localhost:8086.

## 6. Postgres and db_lord

Needs InfluxDB from step 5 and the image from step 2 (`./gitops/local/build-local-images.sh db-lord`).

```bash
helm upgrade --install prod-postgres gitops/apps/platform/prod-postgres \
  -f gitops/apps/platform/prod-postgres/values.yaml \
  -f gitops/apps/platform/prod-postgres/values-local.yaml \
  --namespace prod-postgres --create-namespace
kubectl rollout status statefulset/prod-postgres -n prod-postgres
```

Locally Postgres gets a 2 Gi volume, smaller resources and local-only passwords (`postgres` for the admin, `dblord` for the db_lord user). Only the `dblord` database is created; production also creates `lakefs` for the ML pipeline.

db_lord is installed in **two steps** on the first install:

```bash
# 1. Create the secret and the deployment, skip the migration hook
helm install db-lord gitops/apps/services/db-lord \
  -f gitops/apps/services/db-lord/values.yaml \
  -f gitops/apps/services/db-lord/values-local.yaml \
  --namespace db-lord --create-namespace --no-hooks

# 2. Upgrade: the migration job now runs with the secret in place
helm upgrade db-lord gitops/apps/services/db-lord \
  -f gitops/apps/services/db-lord/values.yaml \
  -f gitops/apps/services/db-lord/values-local.yaml \
  --namespace db-lord --wait --timeout 5m
```

Why: the migration job is a `pre-install` hook, so Helm runs it before it creates the `db-lord-secrets` secret it reads, and a plain first install hangs with `secret "db-lord-secrets" not found`. Later upgrades need only step 2.

The secret is created once and then kept on purpose. After changing `env` in `values-local.yaml`, delete it (`kubectl delete secret db-lord-secrets -n db-lord`) and run both steps again.

Check that db_lord reaches Postgres and InfluxDB:

```bash
kubectl logs -n db-lord job/db-lord-migrate | tail -1   # last alembic migration
kubectl exec -n db-lord deployment/db-lord -- python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/readyz').read().decode())"
# {"status":"healthy","postgres":true,"influx":true}
```

## 7. Traefik (ingress)

Traefik routes requests from the browser to the services. It needs its custom resource definitions first; they are pinned to the Traefik chart release `v28.0.0`, which matches the `traefik:v3.0` image in `gitops/network/ingresscontroller/values.yaml`:

```bash
kubectl apply --server-side -k "https://github.com/traefik/traefik-helm-chart/traefik/crds?ref=v28.0.0"

helm upgrade --install traefik gitops/network/ingresscontroller \
  -f gitops/network/ingresscontroller/values.yaml \
  --namespace ingress --create-namespace

helm upgrade --install traefik-ingress gitops/network/ingress \
  -f gitops/network/ingress/values.yaml \
  --namespace ingress
```

Both charts run with their production defaults; no `values-local.yaml` is needed. Locally everything is served over plain HTTP (`httpOnly: true`), so cert-manager and TLS certificates are not installed.

Traefik's service is of type `LoadBalancer`. Make it reachable on the Mac with a tunnel, in a **second terminal** that stays open (it asks for your password once, to open ports 80 and 443):

```bash
minikube tunnel
```

Check that Traefik answers:

```bash
kubectl get svc traefik -n ingress   # EXTERNAL-IP: 127.0.0.1
curl -i http://localhost/            # 404 page not found: Traefik answers, no routes yet
```

Services are reached under `http://wearables.localhost`. Chrome, Firefox and curl resolve `*.localhost` to the local machine on their own, so no `/etc/hosts` entry is needed. If another browser does not, add `127.0.0.1 wearables.localhost` to `/etc/hosts`.

## 8. importservice

Needs Kafka (step 3), Traefik with a running `minikube tunnel` (step 7) and the image from step 2 (`./gitops/local/build-local-images.sh importservice`).

The importservice checks the app's tokens with a shared secret. The chart expects the secret to exist already, so create it first. `dev-secret` is the same value as in the Docker Compose stack; wearables-bff must use the same value, because it issues the tokens.

```bash
kubectl create namespace importservice
kubectl create secret generic importservice-secrets -n importservice \
  --from-literal=JWT_SECRET=dev-secret

helm upgrade --install importservice gitops/apps/services/importservice \
  -f gitops/apps/services/importservice/values.yaml \
  -f gitops/apps/services/importservice/values-local.yaml \
  --namespace importservice
```

Locally the route listens on `http://wearables.localhost/import/...` over plain HTTP.

```bash
curl http://wearables.localhost/import/health   # {"status":"ok",...}
```

### End-to-end check of the data pipeline

The synthetic data generator from the Docker Compose stack sends readings in the app's format and signs a matching token itself. It currently lives on the `chore/local-init` branch:

```bash
git show chore/local-init:deploy/local/data-generator/generate.py > /tmp/generate.py
python3 /tmp/generate.py --url http://wearables.localhost/import/ingest \
  --patient-id local-patient-1 --backfill-hours 1
```

The readings then travel importservice → Kafka `wearables-raw` → mapper → Kafka `wearables-lp` → Telegraf → InfluxDB. Count them per measurement:

```bash
kubectl exec -n influx deployment/influxdb-deployment -- influx query \
  --org wearables-project --token dev-influx-token \
  'from(bucket:"measurements") |> range(start:-3h)
   |> filter(fn:(r)=> r["device-id"]=="local-patient-1" and r._field!="t_ingested")
   |> group(columns:["_measurement"]) |> count()'
```

One hour of data gives six measurements (heart-rate, steps, distance-walking-running, active and basal energy, respiratory-rate). Rejected records would land in the `dlq` topic:

```bash
kubectl exec -n kafka kafka-dual-role-0 -- \
  bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic dlq   # offsets 0
```

## 9. wearables-bff

Needs db_lord (step 6), Traefik with a running `minikube tunnel` (step 7) and the image from step 2 (`./gitops/local/build-local-images.sh wearables-bff`).

```bash
helm upgrade --install wearables-bff gitops/apps/services/wearables-bff \
  -f gitops/apps/services/wearables-bff/values.yaml \
  -f gitops/apps/services/wearables-bff/values-local.yaml \
  --namespace wearables-bff --create-namespace
```

Local differences:

- `NODE_ENV: development`: login works with the email address alone, no magic-link mail and no Brevo key.
- Admin login: `admin@example.com` (`ADMIN_EMAILS`).
- URLs point to `http://wearables.localhost`; the API is served at `http://wearables.localhost/api`.
- The chart creates its own secret with `JWT_SECRET: dev-secret`, the same value as the importservice secret in step 8, so case tokens issued by the BFF are accepted by the importservice.

Check login and the connection to db_lord:

```bash
curl -c /tmp/bff-cookies -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com"}' http://wearables.localhost/api/login
# {"authenticated":true,"message":"Direct authentication successful",...}

curl -b /tmp/bff-cookies http://wearables.localhost/api/me         # the admin user
curl -b /tmp/bff-cookies http://wearables.localhost/api/patients   # [] (read from db_lord)
```

## 10. Web frontend

Needs wearables-bff (step 9) and the image from step 2 (`./gitops/local/build-local-images.sh web`).

```bash
helm upgrade --install web gitops/apps/web-frontend \
  -f gitops/apps/web-frontend/values.yaml \
  -f gitops/apps/web-frontend/values-local.yaml \
  --namespace web --create-namespace
```

The frontend reads its endpoints from `/runtime-config.js` at runtime. Locally they are relative paths (`/api`, `/proxy`), as in the Docker Compose stack, so the frontend always talks to the host it was loaded from. Traefik sends `/api` to the BFF and everything else to the frontend.

Check it:

```bash
curl -s http://wearables.localhost/runtime-config.js   # API_BASE_URL: "/api", GRAFANA_PROXY_URL: "/proxy"
```

Right after an install Traefik may answer `503 no available server` for a few seconds, until it knows the new pod.

Then open http://wearables.localhost in Chrome or Firefox (with `minikube tunnel` running), log in with `admin@example.com` (no mail in development mode) and create a case. The dashboards on the case page stay empty until Grafana and grafana-proxy are installed.

## 11. Grafana

Needs InfluxDB (step 5).

The web app embeds the patient dashboards through grafana-proxy, which serves Grafana under `/proxy`. Locally Grafana is therefore configured as in the Docker Compose stack:

- it serves itself under `/proxy/` (`server.subPath`), so the paths the proxy forwards match;
- it gets an InfluxDB datasource with the fixed uid `dfa4opgnfgg00e` that the patient dashboards reference (`influxDatasource`);
- the patient dashboards from `observability/dashboards/` are loaded into the folder "Wearables" (`extraDashboardsConfigMap`).

All three are optional chart values and stay off in production. Helm cannot read files outside the chart, so the dashboards go into a ConfigMap first:

```bash
kubectl create namespace grafana
kubectl create configmap grafana-patient-dashboards -n grafana \
  --from-file=observability/dashboards/

helm upgrade --install grafana gitops/apps/monitoring/grafana \
  -f gitops/apps/monitoring/grafana/values.yaml \
  -f gitops/apps/monitoring/grafana/values-local.yaml \
  --namespace grafana
```

After changing a dashboard in `observability/dashboards/`, recreate the ConfigMap (`kubectl create configmap ... --dry-run=client -o yaml | kubectl apply -f -`); Grafana rereads the folder every 60 seconds.

Because Grafana serves under `/proxy/`, its own route `http://wearables.localhost/grafana` does not work locally. Open it with a port-forward instead (login `admin` / `admin`):

```bash
kubectl port-forward -n grafana svc/grafana 3000:3000
# open http://localhost:3000/proxy/  (with /proxy/)
```

Type the full address including `/proxy/`. Plain `http://localhost:3000/` redirects to Grafana's public address `http://wearables.localhost/proxy/`, which only works once grafana-proxy is installed; until then the web frontend answers there with its own "Page not found".

Check the datasource and the dashboards:

```bash
kubectl exec -n grafana deployment/grafana -- wget -qO- \
  "http://admin:admin@localhost:3000/proxy/api/datasources/uid/dfa4opgnfgg00e/health"
# {"message":"datasource is working. ... measurements found","status":"OK"}

kubectl exec -n grafana deployment/grafana -- wget -qO- \
  "http://admin:admin@localhost:3000/proxy/api/search?type=dash-db"
# Platform: Kafka, Wearables Platform Monitoring; Wearables: Dashboard Real, Six Min, ML
```

In the dashboard "Wearables Dashboard Real", enter the patient id used with the data generator (e.g. `local-patient-1`) in the variable "Device / User ID" to see its readings.

## 12. grafana-proxy (dashboards on the case page)

Needs Grafana (step 11), wearables-bff (step 9), the web frontend (step 10) and the image from step 2 (`./gitops/local/build-local-images.sh grafana-proxy`).

The case page loads `/proxy/embed?dashboardUid=...&deviceId=<case token>` in an iframe. The proxy checks that the browser has a web app login session, redirects to the dashboard in kiosk mode and then forwards every request under `/proxy` to Grafana.

The proxy needs a secret with two values: `APP_JWT_SECRET` checks the BFF session and case tokens, so it must be `dev-secret` like the BFF; `GRAFANA_JWT_PRIVATE_KEY` is an RSA key the proxy signs its Grafana requests with (Grafana does not check it at the moment, but the proxy only starts with a valid key).

```bash
kubectl create namespace monitoring
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out /tmp/grafana-jwt.pem
kubectl create secret generic grafana-proxy-secrets -n monitoring \
  --from-file=GRAFANA_JWT_PRIVATE_KEY=/tmp/grafana-jwt.pem \
  --from-literal=APP_JWT_SECRET=dev-secret
rm /tmp/grafana-jwt.pem

helm upgrade --install grafana-proxy gitops/apps/monitoring/grafana-proxy \
  -f gitops/apps/monitoring/grafana-proxy/values.yaml \
  -f gitops/apps/monitoring/grafana-proxy/values-local.yaml \
  --namespace monitoring
```

Locally the proxy addresses Grafana under `/proxy` (`grafana.pathPrefix`, matching `server.subPath` from step 11) and also allows the AI Insights dashboard `adgf864`, which the case page requests.

`http://wearables.localhost/proxy/` answers `401` without a login session; that is expected.

### Check on the case page

Data only shows up for the patient of a case. Read the patient id of your case through the API and send test data for it:

```bash
curl -c /tmp/bff-cookies -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com"}' http://wearables.localhost/api/login
curl -b /tmp/bff-cookies http://wearables.localhost/api/patients   # note the patientId

python3 /tmp/generate.py --url http://wearables.localhost/import/ingest \
  --patient-id <patientId> --backfill-hours 1
```

(`/tmp/generate.py` is the generator from step 8.) Reload the case page: the general data tab shows the readings of the last hour.

## 13. extraction-service

Needs db_lord (step 6), wearables-bff (step 9) and the image from step 2 (`./gitops/local/build-local-images.sh extraction-service`).

```bash
helm upgrade --install extraction-service gitops/apps/services/extraction-service \
  -f gitops/apps/services/extraction-service/values.yaml \
  -f gitops/apps/services/extraction-service/values-local.yaml \
  --namespace extraction-service --create-namespace
```

The extraction-service has no route of its own: the BFF forwards `http://wearables.localhost/api/extraction/...` to it and checks access (a personal API token as Bearer token, or a logged-in admin or researcher). Only the image differs locally.

Check it with the admin session from step 9:

```bash
curl -b /tmp/bff-cookies http://wearables.localhost/api/extraction/v1/measurements/types
# [{"measurement":"active-energy-burned",...},{"measurement":"heart-rate",...},...]
```

Right after an install the first request can fail with `502 Extraction API unavailable` while the service is still being registered; repeat it after a few seconds. The Swagger UI is at http://wearables.localhost/api/extraction/docs.

## 14. Prometheus and db-stats-exporter

The existing operations monitoring: Prometheus scrapes Kafka (Strimzi metrics reporter), the importservice request metrics and the db-stats-exporter, which counts patients, cases and devices in db_lord's Postgres. Needs Kafka (step 3), db_lord (step 6), the importservice (step 8) and Grafana (step 11).

```bash
# Installed into db-lord, so it can read the existing db-lord-secrets
helm upgrade --install db-stats-exporter gitops/apps/monitoring/db-stats-exporter \
  -f gitops/apps/monitoring/db-stats-exporter/values.yaml \
  -f gitops/apps/monitoring/db-stats-exporter/values-local.yaml \
  --namespace db-lord

helm upgrade --install prometheus gitops/apps/monitoring/prometheus \
  -f gitops/apps/monitoring/prometheus/values.yaml \
  -f gitops/apps/monitoring/prometheus/values-local.yaml \
  --namespace monitoring

# Grafana's provisioned Prometheus datasource points to the monitoring namespace
helm upgrade grafana gitops/apps/monitoring/grafana \
  -f gitops/apps/monitoring/grafana/values.yaml \
  -f gitops/apps/monitoring/grafana/values-local.yaml \
  --namespace grafana
```

Locally Prometheus keeps 7 days on a 2 Gi volume (production: 90 days, 5 Gi), and the database counts are refreshed every minute instead of every 15 minutes. `grafana/values-local.yaml` points the Prometheus datasource to `prometheus-service.monitoring`, where Prometheus is installed; the production value in the chart names the namespace `prometheus`.

Check that all targets are up (wait about a minute after the install):

```bash
kubectl exec -n monitoring deployment/prometheus-server -- \
  wget -qO- "http://localhost:9090/api/v1/targets?state=active" | grep -o '"health":"[a-z]*"'
# four times "health":"up": prometheus, kafka-metrics-reporter, importservice, db-stats

kubectl exec -n monitoring deployment/prometheus-server -- \
  wget -qO- "http://localhost:9090/api/v1/query?query=wearables_patients"
# value: number of patients in db_lord
```

The Prometheus UI is available with `kubectl port-forward -n monitoring svc/prometheus-service 9090:80` at http://localhost:9090. The platform dashboards ("Kafka Dashboard", "Wearables Platform Monitoring") are in Grafana's "Platform" folder (step 11).

## 15. cloud-connector

Fetches data from vendor clouds (currently Garmin) and publishes it to Kafka `wearables-raw`, like the importservice does for the app. Needs Kafka (step 3), Traefik with a running `minikube tunnel` (step 7) and the image from step 2 (`./gitops/local/build-local-images.sh cloud-connector`).

```bash
helm upgrade --install cloud-connector gitops/apps/services/cloud-connector \
  -f gitops/apps/services/cloud-connector/values.yaml \
  -f gitops/apps/services/cloud-connector/values-local.yaml \
  --namespace cloud-connector --create-namespace
```

Locally the route listens on `http://wearables.localhost/cloud/...` over plain HTTP, and the linked accounts are kept on a 1 Gi volume (`connections.json`).

```bash
curl http://wearables.localhost/cloud/health        # {"status":"ok","service":"wearables-cloud-connector",...}
curl http://wearables.localhost/cloud/providers     # {"available_providers":["garmin"]}
curl http://wearables.localhost/cloud/connections   # {"connections":[]}
```

Without Garmin credentials only these endpoints are useful locally. Linking an account needs `GARMIN_CLIENT_ID` and `GARMIN_CLIENT_SECRET` in the secret `cloud-connector-secrets` (the chart treats it as optional), and Garmin's OAuth callback and webhooks need a public HTTPS URL, which `wearables.localhost` is not.

The service only connects to Kafka when it publishes. To check that it can reach Kafka anyway:

```bash
kubectl exec -n cloud-connector deploy/cloud-connector -- python -c "
from confluent_kafka.admin import AdminClient
md = AdminClient({'bootstrap.servers':'kafka-kafka-bootstrap.kafka.svc.cluster.local:9092'}).list_topics(timeout=10)
print('wearables-raw' in md.topics)"   # True
```

## 16. Argo CD mode (optional)

Production deploys cloud-connector, importservice, mapper-validator, wearables-bff and the web frontend with Argo CD (`gitops/setup/argocd/`). To try the same locally:

```bash
./gitops/local/setup-local.sh --argocd --revision feat/my-branch   # default revision: main
```

The script then installs Argo CD (pinned to v3.5.7) and applies `gitops/local/argocd/root-app.yaml`. This root application deploys the same chart as production, `gitops/setup/argocd/apps`, with its `values-local.yaml`. The chart creates the five applications: the same as in production, but they pass `values.yaml` plus `values-local.yaml` to the service charts, and deleting one also deletes its resources. The release names are the same as in Helm mode and production (the web frontend's release is `web`). Everything else (Kafka, Postgres, Traefik, Grafana, the secrets, ...) is still installed by Helm.

Use Helm mode (without `--argocd`) for day-to-day development: a change is in the cluster with one `helm upgrade`. Argo CD mode is slower, but behaves like production (automatic sync, self-heal, prune).

### Where things come from

- **Manifests** (chart templates and values files) come from the branch on GitHub given with `--revision`. Argo CD does not see local or unpushed changes: commit and push, then wait for the sync (up to about 3 minutes).
- **Images** come from your machine: every `values-local.yaml` sets `wearables-local/<service>:dev` with pull policy `Never`, so the images built by `build-local-images.sh` from your working tree are used, never the ones built from main.

Check out the same branch locally that you pass as `--revision`, otherwise the manifests and the code in the images come from different branches. After rebuilding an image, Argo CD sees no change (tag and manifest stay the same), so restart the deployment as in Helm mode:

```bash
./gitops/local/build-local-images.sh importservice
kubectl rollout restart deployment/importservice -n importservice
```

### Check

```bash
kubectl get applications -n argocd   # all SYNCED and HEALTHY, including wearables-local-root
helm list -A                         # the five services are not listed: Argo CD renders the charts itself
```

Argo CD UI:

```bash
kubectl port-forward -n argocd svc/argocd-server 8443:443   # https://localhost:8443, user admin
kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' | base64 -d
```

### Working in Argo CD mode

There are no Helm releases for the five services, so `helm uninstall` reports `release not found`. Deleting things by hand has these effects:

| Deleted | Result |
|---|---|
| A resource, e.g. `kubectl delete deployment importservice -n importservice` | Argo CD creates it again within seconds (self-heal). |
| An application, e.g. `kubectl delete application importservice -n argocd` | Its finalizer deletes its resources too, but the root application creates the application again, which then redeploys everything. |
| The root application `wearables-local-root` | All five applications and their resources are removed and stay removed. |
| A namespace | Argo CD recreates the namespace and its resources, but not the secrets created by the script (e.g. `importservice-secrets`); run `setup-local.sh` again. |

Manual changes to a deployment are reverted the same way. To remove an application for good, delete it from `gitops/setup/argocd/apps/values.yaml` and push (prune removes it; this also removes it in production once it is on main). To change things by hand for a while, turn off automated sync for that application in the Argo CD UI first.

### Switching modes

The script switches in both directions:

- `--argocd` uninstalls existing Helm releases of the five services, then Argo CD creates them again.
- A run without `--argocd` deletes the root application, waits until the five applications and their resources are gone, and installs the charts with Helm.

Both cause a short downtime of these services, and the cloud-connector volume (`connections.json`) is created anew. Argo CD itself stays installed in Helm mode, without applications.

## Stopping and resetting

```bash
minikube stop     # pause the cluster, everything is kept
minikube delete   # remove the cluster and all its data
```
