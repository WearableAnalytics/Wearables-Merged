#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BFF_NAMESPACE="${BFF_NAMESPACE:-wearables-bff}"
BFF_SECRET_NAME="${BFF_SECRET_NAME:-wearables-bff-secrets}"
GRAFANA_NAMESPACE="${GRAFANA_NAMESPACE:-monitoring}"
GRAFANA_SECRET_NAME="${GRAFANA_SECRET_NAME:-grafana-auth-secrets}"
GRAFANA_JWT_PRIVATE_KEY_PATH="${GRAFANA_JWT_PRIVATE_KEY_PATH:-${REPO_ROOT}/secrets/grafana-jwt-private.pem}"

BREVO_API_KEY="${BREVO_API_KEY:-}"
RESEARCHER_API_ACCESS_TOKEN="${RESEARCHER_API_ACCESS_TOKEN:-}"
SHARED_APP_JWT_SECRET="${SHARED_APP_JWT_SECRET:-}"
ROTATE_SHARED_APP_JWT_SECRET="${ROTATE_SHARED_APP_JWT_SECRET:-false}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap-runtime-secrets.sh

Environment variables:
  BFF_NAMESPACE                       (default: wearables-bff)
  BFF_SECRET_NAME                     (default: wearables-bff-secrets)
  GRAFANA_NAMESPACE                   (default: monitoring)
  GRAFANA_SECRET_NAME                 (default: grafana-auth-secrets)
  GRAFANA_JWT_PRIVATE_KEY_PATH        (default: ./secrets/grafana-jwt-private.pem)
  BREVO_API_KEY                       (optional)
  RESEARCHER_API_ACCESS_TOKEN         (optional)
  SHARED_APP_JWT_SECRET               (optional; overrides auto-discovery/generation)
  ROTATE_SHARED_APP_JWT_SECRET        (default: false; set true to force new random value)

Behavior:
  - Ensures namespaces exist.
  - Reuses existing JWT secret if found (unless rotation is forced).
  - Generates one shared JWT secret and applies it to:
      * wearables-bff secret key: JWT_SECRET
      * grafana-auth secret key: APP_JWT_SECRET
  - Applies grafana private key from GRAFANA_JWT_PRIVATE_KEY_PATH.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required but not found in PATH." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "Error: openssl is required but not found in PATH." >&2
  exit 1
fi

if [[ ! -f "${GRAFANA_JWT_PRIVATE_KEY_PATH}" ]]; then
  echo "Error: Grafana private key file not found: ${GRAFANA_JWT_PRIVATE_KEY_PATH}" >&2
  exit 1
fi

decode_b64() {
  local encoded="$1"
  if [[ -z "${encoded}" ]]; then
    return 0
  fi
  printf '%s' "${encoded}" | openssl base64 -d -A 2>/dev/null || true
}

read_secret_key() {
  local namespace="$1"
  local secret_name="$2"
  local key="$3"
  local encoded
  encoded="$(kubectl -n "${namespace}" get secret "${secret_name}" -o "jsonpath={.data.${key}}" 2>/dev/null || true)"
  decode_b64 "${encoded}"
}

ensure_namespace() {
  local namespace="$1"
  if ! kubectl get namespace "${namespace}" >/dev/null 2>&1; then
    kubectl create namespace "${namespace}" >/dev/null
    echo "Created namespace: ${namespace}"
  fi
}

select_shared_jwt_secret() {
  local existing_from_bff existing_from_grafana

  if [[ "${ROTATE_SHARED_APP_JWT_SECRET}" == "true" ]]; then
    echo "Rotation enabled: generating a new shared JWT secret." >&2
    openssl rand -base64 48
    return 0
  fi

  if [[ -n "${SHARED_APP_JWT_SECRET}" ]]; then
    echo "Using SHARED_APP_JWT_SECRET from environment." >&2
    printf '%s' "${SHARED_APP_JWT_SECRET}"
    return 0
  fi

  existing_from_bff="$(read_secret_key "${BFF_NAMESPACE}" "${BFF_SECRET_NAME}" "JWT_SECRET")"
  if [[ -n "${existing_from_bff}" ]]; then
    echo "Reusing existing ${BFF_NAMESPACE}/${BFF_SECRET_NAME} JWT_SECRET." >&2
    printf '%s' "${existing_from_bff}"
    return 0
  fi

  existing_from_grafana="$(read_secret_key "${GRAFANA_NAMESPACE}" "${GRAFANA_SECRET_NAME}" "APP_JWT_SECRET")"
  if [[ -n "${existing_from_grafana}" ]]; then
    echo "Reusing existing ${GRAFANA_NAMESPACE}/${GRAFANA_SECRET_NAME} APP_JWT_SECRET." >&2
    printf '%s' "${existing_from_grafana}"
    return 0
  fi

  echo "Generating new shared JWT secret." >&2
  openssl rand -base64 48
}

ensure_namespace "${BFF_NAMESPACE}"
ensure_namespace "${GRAFANA_NAMESPACE}"

SHARED_APP_JWT_SECRET="$(select_shared_jwt_secret)"

kubectl -n "${BFF_NAMESPACE}" create secret generic "${BFF_SECRET_NAME}" \
  --from-literal=JWT_SECRET="${SHARED_APP_JWT_SECRET}" \
  --from-literal=BREVO_API_KEY="${BREVO_API_KEY}" \
  --from-literal=RESEARCHER_API_ACCESS_TOKEN="${RESEARCHER_API_ACCESS_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "${GRAFANA_NAMESPACE}" create secret generic "${GRAFANA_SECRET_NAME}" \
  --from-file=GRAFANA_JWT_PRIVATE_KEY="${GRAFANA_JWT_PRIVATE_KEY_PATH}" \
  --from-literal=APP_JWT_SECRET="${SHARED_APP_JWT_SECRET}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "Applied secrets:"
echo "  - ${BFF_NAMESPACE}/${BFF_SECRET_NAME} (JWT_SECRET, BREVO_API_KEY, RESEARCHER_API_ACCESS_TOKEN)"
echo "  - ${GRAFANA_NAMESPACE}/${GRAFANA_SECRET_NAME} (GRAFANA_JWT_PRIVATE_KEY, APP_JWT_SECRET)"
