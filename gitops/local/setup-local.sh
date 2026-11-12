#!/usr/bin/env bash
set -euo pipefail

# Sets up the whole platform on the local minikube cluster, following the steps
# in gitops/local/README.md. Safe to run again: Helm upgrades the releases, and
# secrets are only created when they are missing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APPS="${REPO_ROOT}/gitops/apps"
NETWORK="${REPO_ROOT}/gitops/network"

# Every kubectl and helm call is pinned to this context, so nothing can end up
# in another cluster, even if the current context changes while this runs.
CONTEXT="minikube"
TIMEOUT="10m"

# Pinned versions (see README): Strimzi 0.49.0-1.0.0 support Kafka 4.1.0 and the
# kafka.strimzi.io/v1 API; Traefik chart v28.0.0 matches the traefik:v3.0 image.
STRIMZI_VERSION="1.0.0"
TRAEFIK_CRDS="https://github.com/traefik/traefik-helm-chart/traefik/crds?ref=v28.0.0"
ARGOCD_VERSION="v3.5.7"
ARGOCD_MANIFEST="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"

# The applications Argo CD manages in --argocd mode, the same as in production
# (gitops/setup/argocd/apps/values.yaml), as <Argo CD application>:<Helm release>:<namespace>.
ARGOCD_APPS=(
  "prod-postgres:prod-postgres:prod-postgres"
  "influxdb:influxdb:influx"
  "kafka:kafka:kafka"
  "db-lord:db-lord:db-lord"
  "extraction-service:extraction-service:extraction-service"
  "cloud-connector:cloud-connector:cloud-connector"
  "importservice:importservice:importservice"
  "mapper-validator:mapper-validator:kafka"
  "wearables-bff:wearables-bff:wearables-bff"
  "web-frontend:web:web"
  "grafana:grafana:grafana"
  "grafana-proxy:grafana-proxy:monitoring"
)

SKIP_BUILD=false
USE_ARGOCD=false
REVISION=""

usage() {
  cat <<'EOF'
Usage:
  ./gitops/local/setup-local.sh [--skip-build] [--argocd [--revision <branch>]]

Builds the service images into minikube and installs every chart with its
values-local.yaml, in the order of gitops/local/README.md.

Options:
  --skip-build          do not rebuild the service images
  --argocd              let Argo CD deploy the applications from GitHub, as in
                        production (gitops/setup/argocd/apps); the script only
                        installs Strimzi, Traefik, the secrets, Telegraf,
                        Prometheus and db-stats-exporter
  --revision <branch>   the branch Argo CD reads from (default: main); it must
                        be pushed, Argo CD does not see local changes
  -h, --help            show this help

Switching between the modes replaces these deployments: --argocd removes their
Helm releases, a run without --argocd removes their Argo CD applications. The
data of Postgres, InfluxDB, Kafka and Grafana is lost on a switch.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

step() {
  echo
  echo "==> $*"
}

k() { kubectl --context "$CONTEXT" "$@"; }
h() { helm --kube-context "$CONTEXT" "$@"; }

ensure_namespace() {
  k get namespace "$1" >/dev/null 2>&1 || k create namespace "$1"
}

# install_chart <release> <chart dir> <namespace> [extra helm args]
# Uses the chart's values.yaml plus values-local.yaml next to it.
install_chart() {
  local release="$1" chart="$2" namespace="$3"
  shift 3
  h upgrade --install "$release" "$chart" \
    -f "${chart}/values.yaml" \
    -f "${chart}/values-local.yaml" \
    --namespace "$namespace" --create-namespace \
    --wait --timeout "$TIMEOUT" "$@"
}

# keep_secret <namespace> <secret>
# Older versions of the prod-postgres and wearables-bff charts created their
# secret themselves; without this, the next helm upgrade of an existing release
# would delete it.
keep_secret() {
  k annotate secret "$2" -n "$1" helm.sh/resource-policy=keep --overwrite >/dev/null
}

install_strimzi() {
  h upgrade --install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator \
    --version "$STRIMZI_VERSION" --namespace kafka --create-namespace --wait --timeout "$TIMEOUT"
}

install_traefik() {
  k apply --server-side -k "$TRAEFIK_CRDS" >/dev/null
  h upgrade --install traefik "${NETWORK}/ingresscontroller" \
    -f "${NETWORK}/ingresscontroller/values.yaml" \
    --namespace ingress --create-namespace --wait --timeout "$TIMEOUT"
  h upgrade --install traefik-ingress "${NETWORK}/ingress" \
    -f "${NETWORK}/ingress/values.yaml" \
    --namespace ingress --wait --timeout "$TIMEOUT"
}

create_importservice_secret() {
  ensure_namespace importservice
  if ! k get secret importservice-secrets -n importservice >/dev/null 2>&1; then
    # Same value as the BFF's JWT_SECRET, which issues the case tokens.
    k create secret generic importservice-secrets -n importservice \
      --from-literal=JWT_SECRET=dev-secret
  fi
}

# The wearables-bff chart does not create its secret (as in production).
# JWT_SECRET is the same as the importservice's and grafana-proxy's: the BFF
# issues the tokens they check. No Brevo key: locally no mails are sent.
create_bff_secret() {
  ensure_namespace wearables-bff
  if ! k get secret wearables-bff-secrets -n wearables-bff >/dev/null 2>&1; then
    k create secret generic wearables-bff-secrets -n wearables-bff \
      --from-literal=JWT_SECRET=dev-secret \
      --from-literal=BREVO_API_KEY=disabled
  fi
  keep_secret wearables-bff wearables-bff-secrets
}

# Same name as in production (secret.name in the grafana-proxy values.yaml).
create_grafana_proxy_secret() {
  ensure_namespace monitoring
  if ! k get secret grafana-auth-secrets -n monitoring >/dev/null 2>&1; then
    key_file="$(mktemp)"
    trap 'rm -f "$key_file"' EXIT
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$key_file" 2>/dev/null
    k create secret generic grafana-auth-secrets -n monitoring \
      --from-file=GRAFANA_JWT_PRIVATE_KEY="$key_file" \
      --from-literal=APP_JWT_SECRET=dev-secret
    rm -f "$key_file"
  fi
}

# Applied on every run, so dashboard changes in observability/dashboards are picked up.
apply_grafana_dashboards() {
  ensure_namespace grafana
  k create configmap grafana-patient-dashboards -n grafana \
    --from-file="${REPO_ROOT}/observability/dashboards/" \
    --dry-run=client -o yaml | k apply -f - >/dev/null
}

# The prod-postgres chart does not create its secret (as in production).
create_postgres_secret() {
  ensure_namespace prod-postgres
  if ! k get secret prod-postgres-secret -n prod-postgres >/dev/null 2>&1; then
    k create secret generic prod-postgres-secret -n prod-postgres \
      --from-literal=POSTGRES_PASSWORD=postgres
  fi
  keep_secret prod-postgres prod-postgres-secret
}

# The db-lord chart does not create its secret (as in production). The values
# match the local Postgres (prod-postgres values-local) and InfluxDB
# (influxdb initSetup in values-local).
create_db_lord_secret() {
  ensure_namespace db-lord
  if ! k get secret db-lord-secrets -n db-lord >/dev/null 2>&1; then
    k create secret generic db-lord-secrets -n db-lord \
      --from-literal=POSTGRES_SERVER=prod-postgres.prod-postgres.svc.cluster.local \
      --from-literal=POSTGRES_PORT=5432 \
      --from-literal=POSTGRES_DB=dblord \
      --from-literal=POSTGRES_USER=dblord \
      --from-literal=POSTGRES_PASSWORD=dblord \
      --from-literal=INFLUX_URL=http://influxdb-service.influx.svc.cluster.local:8086 \
      --from-literal=INFLUX_ORG=wearables-project \
      --from-literal=INFLUX_BUCKET=measurements \
      --from-literal=INFLUX_TOKEN=dev-influx-token
  fi
}

argocd_root_exists() {
  k get applications.argoproj.io wearables-local-root -n argocd >/dev/null 2>&1
}

# Helm mode on a cluster set up with --argocd: delete the applications. Their
# finalizers make Argo CD delete the deployed resources first.
remove_argocd_apps() {
  argocd_root_exists || return 0
  step "Removing the Argo CD applications (switching to Helm mode)"
  k delete applications.argoproj.io wearables-local-root -n argocd --timeout="$TIMEOUT"
  local entry
  for entry in "${ARGOCD_APPS[@]}"; do
    k wait applications.argoproj.io/"${entry%%:*}" -n argocd --for=delete --timeout="$TIMEOUT" >/dev/null 2>&1 || true
  done
}

# --argocd on a cluster set up in Helm mode: uninstall the Helm releases, so
# Argo CD creates the resources itself.
remove_helm_releases() {
  local entry rest release namespace
  for entry in "${ARGOCD_APPS[@]}"; do
    rest="${entry#*:}"
    release="${rest%%:*}"
    namespace="${rest#*:}"
    if h status "$release" --namespace "$namespace" >/dev/null 2>&1; then
      echo "uninstalling Helm release ${release} (${namespace})"
      h uninstall "$release" --namespace "$namespace" --wait --timeout "$TIMEOUT"
    fi
  done
}

install_argocd() {
  step "Argo CD ${ARGOCD_VERSION} (reading ${REVISION} from GitHub)"
  ensure_namespace argocd
  # Server-side apply: the CRDs are too large for the client-side annotation.
  k apply -n argocd --server-side --force-conflicts -f "$ARGOCD_MANIFEST" >/dev/null
  k wait -n argocd deployment --all --for=condition=Available --timeout="$TIMEOUT"
  k rollout status -n argocd statefulset/argocd-application-controller --timeout="$TIMEOUT"

  sed "s|__REVISION__|${REVISION}|g" "${SCRIPT_DIR}/argocd/root-app.yaml" | k apply -f -

  local entry app
  for entry in "${ARGOCD_APPS[@]}"; do
    app="${entry%%:*}"
    echo "waiting for ${app}"
    # The root application creates the others; kubectl wait needs them to exist.
    until k get applications.argoproj.io "$app" -n argocd >/dev/null 2>&1; do sleep 2; done
    k wait applications.argoproj.io/"$app" -n argocd \
      --for=jsonpath='{.status.sync.status}'=Synced --timeout="$TIMEOUT" >/dev/null
    k wait applications.argoproj.io/"$app" -n argocd \
      --for=jsonpath='{.status.health.status}'=Healthy --timeout="$TIMEOUT" >/dev/null
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) SKIP_BUILD=true; shift ;;
    --argocd) USE_ARGOCD=true; shift ;;
    --revision)
      [[ $# -ge 2 ]] || die "--revision needs a branch"
      REVISION="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

if [[ -n "$REVISION" ]] && ! $USE_ARGOCD; then
  die "--revision only works together with --argocd"
fi
REVISION="${REVISION:-main}"

for tool in minikube kubectl helm openssl; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required"
done
minikube status >/dev/null 2>&1 || die "minikube is not running (start it with: minikube start --driver=docker --cpus=4 --memory=8g --disk-size=40g)"
k get nodes >/dev/null 2>&1 || die "kubectl context '$CONTEXT' is not reachable"

if ! $SKIP_BUILD; then
  step "Building service images into minikube"
  "${SCRIPT_DIR}/build-local-images.sh"
fi

if $USE_ARGOCD; then
  remove_helm_releases
else
  remove_argocd_apps
fi

if $USE_ARGOCD; then
  # As in production: the script only installs what the applications need
  # beforehand, Argo CD deploys the applications.
  step "Kafka operator (Strimzi ${STRIMZI_VERSION})"
  install_strimzi

  step "Traefik"
  install_traefik

  step "Secrets and Grafana dashboards"
  create_importservice_secret
  create_postgres_secret
  create_db_lord_secret
  create_bff_secret
  create_grafana_proxy_secret
  apply_grafana_dashboards

  install_argocd

  # Not managed by Argo CD in production either.
  step "Telegraf, Prometheus and db-stats-exporter"
  install_chart telegraf "${APPS}/monitoring/telegraf" telegraf
  install_chart db-stats-exporter "${APPS}/monitoring/db-stats-exporter" db-lord
  install_chart prometheus "${APPS}/monitoring/prometheus" monitoring
else
  step "Kafka (Strimzi ${STRIMZI_VERSION})"
  install_strimzi
  install_chart kafka "${APPS}/platform/kafka" kafka
  # Helm does not wait for the Kafka custom resource; Strimzi reports readiness on it.
  k wait -n kafka kafka/kafka --for=condition=Ready --timeout="$TIMEOUT"

  step "FHIR mapper"
  install_chart mapper-validator "${APPS}/services/mapper-validator" kafka

  step "InfluxDB and Telegraf"
  install_chart influxdb "${APPS}/monitoring/influxdb" influx
  install_chart telegraf "${APPS}/monitoring/telegraf" telegraf

  step "Postgres and db_lord"
  create_postgres_secret
  install_chart prod-postgres "${APPS}/platform/prod-postgres" prod-postgres
  create_db_lord_secret
  install_chart db-lord "${APPS}/services/db-lord" db-lord

  step "Traefik"
  install_traefik

  step "importservice"
  create_importservice_secret
  install_chart importservice "${APPS}/services/importservice" importservice

  step "wearables-bff and web frontend"
  create_bff_secret
  install_chart wearables-bff "${APPS}/services/wearables-bff" wearables-bff
  install_chart web "${APPS}/web-frontend" web

  step "Grafana and grafana-proxy"
  apply_grafana_dashboards
  install_chart grafana "${APPS}/monitoring/grafana" grafana
  create_grafana_proxy_secret
  install_chart grafana-proxy "${APPS}/monitoring/grafana-proxy" monitoring

  step "extraction-service"
  install_chart extraction-service "${APPS}/services/extraction-service" extraction-service

  step "Prometheus and db-stats-exporter"
  install_chart db-stats-exporter "${APPS}/monitoring/db-stats-exporter" db-lord
  install_chart prometheus "${APPS}/monitoring/prometheus" monitoring

  step "cloud-connector"
  install_chart cloud-connector "${APPS}/services/cloud-connector" cloud-connector
fi

step "Done"
k get pods -A
cat <<'EOF'

Next:
  1. In a second terminal, keep this running (asks for your password once):
       minikube tunnel
  2. Open http://wearables.localhost and log in with admin@example.com
EOF
if $USE_ARGOCD; then
  cat <<'EOF'
  3. Argo CD UI: kubectl port-forward -n argocd svc/argocd-server 8443:443
     and open https://localhost:8443 (user admin, password:
       kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' | base64 -d)
EOF
fi
