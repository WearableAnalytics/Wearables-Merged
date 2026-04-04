#!/usr/bin/env bash
# =============================================================================
# helm-deploy.sh – Deploy all Wearables Helm charts in the correct order
#
# Usage:
#   ./infra/helm-deploy.sh [--dry-run]
#
# Prerequisites: helm, kubectl configured and pointing at the target cluster
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CHARTS_DIR="${REPO_ROOT}/gitops/apps"
NETWORK_DIR="${REPO_ROOT}/gitops/network"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "🔍 Dry-run mode – no changes will be applied"
fi

# Source .env if present
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "${SCRIPT_DIR}/.env" && set +a
fi

DOMAIN="${DOMAIN:-wearables.charite.de}"
CERT_EMAIL="${CERT_EMAIL:-admin@charite.de}"
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-$(openssl rand -base64 16)}"
POSTGRES_DEV_PASSWORD="${POSTGRES_DEV_PASSWORD:-$(openssl rand -base64 16)}"
POSTGRES_PROD_PASSWORD="${POSTGRES_PROD_PASSWORD:-$(openssl rand -base64 16)}"

helm_install() {
  local release="$1"
  local chart_path="$2"
  local namespace="$3"
  shift 3
  local extra_args=("$@")

  echo ""
  echo "▶  helm upgrade --install ${release} (ns: ${namespace})"

  if $DRY_RUN; then
    echo "   [dry-run] helm upgrade --install ${release} ${chart_path} -n ${namespace} --create-namespace ${extra_args[*]:-}"
    return
  fi

  helm upgrade --install "${release}" "${chart_path}" \
    --namespace "${namespace}" \
    --create-namespace \
    --wait \
    --timeout 5m \
    "${extra_args[@]:-}"
}

wait_for_crds() {
  local crds=("$@")
  echo "⏳ Waiting for CRDs: ${crds[*]}"
  for crd in "${crds[@]}"; do
    until kubectl get crd "${crd}" >/dev/null 2>&1; do
      echo "   waiting for CRD ${crd}..."
      sleep 5
    done
    echo "   ✓ ${crd}"
  done
}

# ── 0. External operators (install from Helm repos) ─────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Phase 0: External operators"
echo "═══════════════════════════════════════════════════"

if ! $DRY_RUN; then
  # cert-manager
  helm repo add jetstack https://charts.jetstack.io --force-update
  helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager --create-namespace \
    --version v1.14.0 \
    --set installCRDs=true \
    --wait --timeout 5m
  echo "✓ cert-manager"

  # Strimzi (Kafka operator)
  helm repo add strimzi https://strimzi.io/charts/ --force-update
  helm upgrade --install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
    --namespace kafka --create-namespace \
    --wait --timeout 5m
  echo "✓ Strimzi Kafka Operator"

  wait_for_crds \
    "kafkas.kafka.strimzi.io" \
    "kafkatopics.kafka.strimzi.io" \
    "certificates.cert-manager.io"
else
  echo "[dry-run] would install: cert-manager, strimzi-kafka-operator"
fi

# ── 1. Network layer ─────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Phase 1: Network (Traefik + cert-manager issuer)"
echo "═══════════════════════════════════════════════════"

helm_install traefik "${NETWORK_DIR}/ingresscontroller" traefik \
  --set "clusterIssuer.email=${CERT_EMAIL}"

helm_install ingress "${NETWORK_DIR}/ingress" traefik \
  --set "domain=${DOMAIN}"

# ── 2. Platform services ─────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Phase 2: Platform (Postgres, Mosquitto, Kafka)"
echo "═══════════════════════════════════════════════════"

helm_install postgres "${CHARTS_DIR}/platform/postgres" wearables \
  --set "postgres.password=${POSTGRES_DEV_PASSWORD}"

helm_install prod-postgres "${CHARTS_DIR}/platform/prod-postgres" wearables \
  --set "auth.postgresPassword=${POSTGRES_PROD_PASSWORD}"

helm_install mosquitto "${CHARTS_DIR}/platform/mosquitto" wearables

helm_install kafka "${CHARTS_DIR}/platform/kafka" kafka

# ── 3. Backend services ───────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Phase 3: Backend Services"
echo "═══════════════════════════════════════════════════"

helm_install importservice "${CHARTS_DIR}/services/importservice" wearables \
  --set "env.JWT_SECRET=${SHARED_APP_JWT_SECRET:-$(openssl rand -base64 32)}"

helm_install db-lord "${CHARTS_DIR}/services/db-lord" wearables

helm_install extraction-service "${CHARTS_DIR}/services/extraction-service" wearables

helm_install mapper-validator "${CHARTS_DIR}/services/mapper-validator" wearables

helm_install wearables-bff "${CHARTS_DIR}/services/wearables-bff" wearables-bff

# ── 4. Monitoring ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Phase 4: Monitoring (InfluxDB, Prometheus, Grafana)"
echo "═══════════════════════════════════════════════════"

helm_install influxdb "${CHARTS_DIR}/monitoring/influxdb" monitoring

helm_install prometheus "${CHARTS_DIR}/monitoring/prometheus" monitoring

helm_install grafana "${CHARTS_DIR}/monitoring/grafana" monitoring \
  --set "adminPassword=${GRAFANA_ADMIN_PASSWORD}"

helm_install telegraf "${CHARTS_DIR}/monitoring/telegraf" monitoring

helm_install grafana-proxy "${CHARTS_DIR}/monitoring/grafana-proxy" monitoring

# ── 5. Web Frontend ───────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Phase 5: Web Frontend"
echo "═══════════════════════════════════════════════════"

helm_install web-frontend "${CHARTS_DIR}/web-frontend" wearables \
  --set "domain=${DOMAIN}"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " ✅ All charts deployed"
echo "═══════════════════════════════════════════════════"
echo ""
echo "Cluster status:"
kubectl get pods -A --field-selector=status.phase!=Running 2>/dev/null | head -30 || true
echo ""
echo "Ingress endpoints:"
kubectl get ingressroute -A 2>/dev/null || kubectl get ingress -A 2>/dev/null || true
