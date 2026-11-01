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

SKIP_BUILD=false

usage() {
  cat <<'EOF'
Usage:
  ./gitops/local/setup-local.sh [--skip-build]

Builds the service images into minikube and installs every chart with its
values-local.yaml, in the order of gitops/local/README.md.

Options:
  --skip-build   do not rebuild the service images
  -h, --help     show this help
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) SKIP_BUILD=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

for tool in minikube kubectl helm openssl; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required"
done
minikube status >/dev/null 2>&1 || die "minikube is not running (start it with: minikube start --driver=docker --cpus=4 --memory=8g --disk-size=40g)"
k get nodes >/dev/null 2>&1 || die "kubectl context '$CONTEXT' is not reachable"

if ! $SKIP_BUILD; then
  step "Building service images into minikube"
  "${SCRIPT_DIR}/build-local-images.sh"
fi

step "Kafka (Strimzi ${STRIMZI_VERSION})"
h upgrade --install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator \
  --version "$STRIMZI_VERSION" --namespace kafka --create-namespace --wait --timeout "$TIMEOUT"
install_chart kafka "${APPS}/platform/kafka" kafka
# Helm does not wait for the Kafka custom resource; Strimzi reports readiness on it.
k wait -n kafka kafka/kafka --for=condition=Ready --timeout="$TIMEOUT"

step "FHIR mapper"
install_chart mapper-validator "${APPS}/services/mapper-validator" kafka

step "InfluxDB and Telegraf"
install_chart influxdb "${APPS}/monitoring/influxdb" influx
install_chart telegraf "${APPS}/monitoring/telegraf" telegraf

step "Postgres and db_lord"
install_chart prod-postgres "${APPS}/platform/prod-postgres" prod-postgres
# The migration job is a pre-install hook that needs db-lord-secrets, which the
# chart only creates during the install itself; so the first install skips hooks.
if ! h status db-lord --namespace db-lord >/dev/null 2>&1; then
  h install db-lord "${APPS}/services/db-lord" \
    -f "${APPS}/services/db-lord/values.yaml" \
    -f "${APPS}/services/db-lord/values-local.yaml" \
    --namespace db-lord --create-namespace --no-hooks
fi
install_chart db-lord "${APPS}/services/db-lord" db-lord

step "Traefik"
k apply --server-side -k "$TRAEFIK_CRDS" >/dev/null
h upgrade --install traefik "${NETWORK}/ingresscontroller" \
  -f "${NETWORK}/ingresscontroller/values.yaml" \
  --namespace ingress --create-namespace --wait --timeout "$TIMEOUT"
h upgrade --install traefik-ingress "${NETWORK}/ingress" \
  -f "${NETWORK}/ingress/values.yaml" \
  --namespace ingress --wait --timeout "$TIMEOUT"

step "importservice"
ensure_namespace importservice
if ! k get secret importservice-secrets -n importservice >/dev/null 2>&1; then
  # Same value as the BFF's JWT_SECRET, which issues the case tokens.
  k create secret generic importservice-secrets -n importservice \
    --from-literal=JWT_SECRET=dev-secret
fi
install_chart importservice "${APPS}/services/importservice" importservice

step "wearables-bff and web frontend"
install_chart wearables-bff "${APPS}/services/wearables-bff" wearables-bff
install_chart web "${APPS}/web-frontend" web

step "Grafana and grafana-proxy"
ensure_namespace grafana
# Applied on every run, so dashboard changes in observability/dashboards are picked up.
k create configmap grafana-patient-dashboards -n grafana \
  --from-file="${REPO_ROOT}/observability/dashboards/" \
  --dry-run=client -o yaml | k apply -f - >/dev/null
install_chart grafana "${APPS}/monitoring/grafana" grafana

ensure_namespace monitoring
if ! k get secret grafana-proxy-secrets -n monitoring >/dev/null 2>&1; then
  key_file="$(mktemp)"
  trap 'rm -f "$key_file"' EXIT
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$key_file" 2>/dev/null
  k create secret generic grafana-proxy-secrets -n monitoring \
    --from-file=GRAFANA_JWT_PRIVATE_KEY="$key_file" \
    --from-literal=APP_JWT_SECRET=dev-secret
  rm -f "$key_file"
fi
install_chart grafana-proxy "${APPS}/monitoring/grafana-proxy" monitoring

step "extraction-service"
install_chart extraction-service "${APPS}/services/extraction-service" extraction-service

step "Prometheus and db-stats-exporter"
install_chart db-stats-exporter "${APPS}/monitoring/db-stats-exporter" db-lord
install_chart prometheus "${APPS}/monitoring/prometheus" monitoring

step "Done"
k get pods -A
cat <<'EOF'

Next:
  1. In a second terminal, keep this running (asks for your password once):
       minikube tunnel
  2. Open http://wearables.localhost and log in with admin@example.com
EOF
