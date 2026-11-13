#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BFF_NAMESPACE="${BFF_NAMESPACE:-wearables-bff}"
BFF_SECRET_NAME="${BFF_SECRET_NAME:-wearables-bff-secrets}"
GRAFANA_NAMESPACE="${GRAFANA_NAMESPACE:-monitoring}"
GRAFANA_SECRET_NAME="${GRAFANA_SECRET_NAME:-grafana-auth-secrets}"
GRAFANA_JWT_PRIVATE_KEY_PATH="${GRAFANA_JWT_PRIVATE_KEY_PATH:-${REPO_ROOT}/secrets/grafana-jwt-private.pem}"
GENERATE_GRAFANA_JWT_PRIVATE_KEY_IF_MISSING="${GENERATE_GRAFANA_JWT_PRIVATE_KEY_IF_MISSING:-true}"
PROD_POSTGRES_NAMESPACE="${PROD_POSTGRES_NAMESPACE:-prod-postgres}"
PROD_POSTGRES_SECRET_NAME="${PROD_POSTGRES_SECRET_NAME:-prod-postgres-secret}"
DB_LORD_NAMESPACE="${DB_LORD_NAMESPACE:-db-lord}"
DB_LORD_SECRET_NAME="${DB_LORD_SECRET_NAME:-db-lord-secrets}"
# The Influx settings of db-lord default to the ones of Telegraf.
DB_LORD_INFLUX_ORG="${DB_LORD_INFLUX_ORG:-${INFLUX_ORG:-}}"
DB_LORD_INFLUX_BUCKET="${DB_LORD_INFLUX_BUCKET:-${INFLUX_BUCKET:-}}"
DB_LORD_INFLUX_TOKEN="${DB_LORD_INFLUX_TOKEN:-${INFLUX_TOKEN:-}}"
CLOUD_CONNECTOR_NAMESPACE="${CLOUD_CONNECTOR_NAMESPACE:-cloud-connector}"
CLOUD_CONNECTOR_SECRET_NAME="${CLOUD_CONNECTOR_SECRET_NAME:-cloud-connector-secrets}"
GARMIN_CLIENT_ID="${GARMIN_CLIENT_ID:-}"
GARMIN_CLIENT_SECRET="${GARMIN_CLIENT_SECRET:-}"

BREVO_API_KEY="${BREVO_API_KEY:-}"
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
  GENERATE_GRAFANA_JWT_PRIVATE_KEY_IF_MISSING (default: false; set true to generate RSA key if missing)
  BREVO_API_KEY                       (optional)
  SHARED_APP_JWT_SECRET               (optional; overrides auto-discovery/generation)
  ROTATE_SHARED_APP_JWT_SECRET        (default: false; set true to force new random value)
  PROD_POSTGRES_PASSWORD              (admin password of prod-postgres)
  PROD_POSTGRES_NAMESPACE             (default: prod-postgres)
  PROD_POSTGRES_SECRET_NAME           (default: prod-postgres-secret)
  DB_LORD_NAMESPACE                   (default: db-lord)
  DB_LORD_SECRET_NAME                 (default: db-lord-secrets)
  DB_LORD_POSTGRES_SERVER, DB_LORD_POSTGRES_PORT, DB_LORD_POSTGRES_DB,
  DB_LORD_POSTGRES_USER, DB_LORD_POSTGRES_PASSWORD, DB_LORD_INFLUX_URL
  DB_LORD_INFLUX_ORG, DB_LORD_INFLUX_BUCKET, DB_LORD_INFLUX_TOKEN
                                      (default: INFLUX_ORG, INFLUX_BUCKET, INFLUX_TOKEN)
  GARMIN_CLIENT_ID, GARMIN_CLIENT_SECRET (optional; Garmin OAuth app of cloud-connector)
  CLOUD_CONNECTOR_NAMESPACE           (default: cloud-connector)
  CLOUD_CONNECTOR_SECRET_NAME         (default: cloud-connector-secrets)

Behavior:
  - Ensures namespaces exist.
  - Reuses existing JWT secret if found (unless rotation is forced).
  - Generates one shared JWT secret and applies it to:
      * wearables-bff secret key: JWT_SECRET
      * grafana-auth secret key: APP_JWT_SECRET
  - Applies grafana private key from GRAFANA_JWT_PRIVATE_KEY_PATH.
  - Optionally generates a new RSA private key at GRAFANA_JWT_PRIVATE_KEY_PATH when missing.
  - Applies the prod-postgres secret from PROD_POSTGRES_PASSWORD and the db-lord
    secret from the DB_LORD_* variables; their charts do not create them.
    Without all of a secret's variables set, an existing secret is kept.
  - Applies the Garmin keys of the cloud-connector secret when both GARMIN_*
    variables are set; other keys of that secret (JWT_SECRET) are left as they are.
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

ensure_grafana_private_key_file() {
  if [[ -f "${GRAFANA_JWT_PRIVATE_KEY_PATH}" ]]; then
    return 0
  fi

  if [[ "${GENERATE_GRAFANA_JWT_PRIVATE_KEY_IF_MISSING}" == "true" ]]; then
    mkdir -p "$(dirname "${GRAFANA_JWT_PRIVATE_KEY_PATH}")"
    echo "Grafana private key not found; generating RSA key at ${GRAFANA_JWT_PRIVATE_KEY_PATH}." >&2
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "${GRAFANA_JWT_PRIVATE_KEY_PATH}" >/dev/null
    chmod 600 "${GRAFANA_JWT_PRIVATE_KEY_PATH}"
    return 0
  fi

  echo "Error: Grafana private key file not found: ${GRAFANA_JWT_PRIVATE_KEY_PATH}" >&2
  echo "Set GENERATE_GRAFANA_JWT_PRIVATE_KEY_IF_MISSING=true to create it automatically." >&2
  exit 1
}

ensure_grafana_private_key_file

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
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "${GRAFANA_NAMESPACE}" create secret generic "${GRAFANA_SECRET_NAME}" \
  --from-file=GRAFANA_JWT_PRIVATE_KEY="${GRAFANA_JWT_PRIVATE_KEY_PATH}" \
  --from-literal=APP_JWT_SECRET="${SHARED_APP_JWT_SECRET}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "Applied secrets:"
echo "  - ${BFF_NAMESPACE}/${BFF_SECRET_NAME} (JWT_SECRET, BREVO_API_KEY)"
echo "  - ${GRAFANA_NAMESPACE}/${GRAFANA_SECRET_NAME} (GRAFANA_JWT_PRIVATE_KEY, APP_JWT_SECRET)"

DB_LORD_VARS=(
  DB_LORD_POSTGRES_SERVER DB_LORD_POSTGRES_PORT DB_LORD_POSTGRES_DB
  DB_LORD_POSTGRES_USER DB_LORD_POSTGRES_PASSWORD DB_LORD_INFLUX_URL
  DB_LORD_INFLUX_ORG DB_LORD_INFLUX_BUCKET DB_LORD_INFLUX_TOKEN
)

# secret_vars_set <namespace> <secret name> <variable...>
# Succeeds when all variables are set, so the caller applies the secret. If not,
# an existing secret is kept (returns 1); without one, the script stops.
secret_vars_set() {
  local namespace="$1" secret_name="$2" var
  shift 2
  local missing=()
  for var in "$@"; do
    [[ -n "${!var:-}" ]] || missing+=("${var}")
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi
  if kubectl -n "${namespace}" get secret "${secret_name}" >/dev/null 2>&1; then
    echo "  - kept existing ${namespace}/${secret_name} (not set: ${missing[*]})"
    return 1
  fi
  echo "Error: ${namespace}/${secret_name} does not exist and these variables are not set: ${missing[*]}" >&2
  exit 1
}

if secret_vars_set "${PROD_POSTGRES_NAMESPACE}" "${PROD_POSTGRES_SECRET_NAME}" PROD_POSTGRES_PASSWORD; then
  ensure_namespace "${PROD_POSTGRES_NAMESPACE}"
  kubectl -n "${PROD_POSTGRES_NAMESPACE}" create secret generic "${PROD_POSTGRES_SECRET_NAME}" \
    --from-literal=POSTGRES_PASSWORD="${PROD_POSTGRES_PASSWORD}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  echo "  - ${PROD_POSTGRES_NAMESPACE}/${PROD_POSTGRES_SECRET_NAME} (POSTGRES_PASSWORD)"
fi
# Older versions of the chart created this secret with Helm; without this, a
# later helm upgrade of the release would delete it.
kubectl -n "${PROD_POSTGRES_NAMESPACE}" annotate secret "${PROD_POSTGRES_SECRET_NAME}" \
  helm.sh/resource-policy=keep --overwrite >/dev/null

if secret_vars_set "${DB_LORD_NAMESPACE}" "${DB_LORD_SECRET_NAME}" "${DB_LORD_VARS[@]}"; then
  ensure_namespace "${DB_LORD_NAMESPACE}"
  kubectl -n "${DB_LORD_NAMESPACE}" create secret generic "${DB_LORD_SECRET_NAME}" \
    --from-literal=POSTGRES_SERVER="${DB_LORD_POSTGRES_SERVER}" \
    --from-literal=POSTGRES_PORT="${DB_LORD_POSTGRES_PORT}" \
    --from-literal=POSTGRES_DB="${DB_LORD_POSTGRES_DB}" \
    --from-literal=POSTGRES_USER="${DB_LORD_POSTGRES_USER}" \
    --from-literal=POSTGRES_PASSWORD="${DB_LORD_POSTGRES_PASSWORD}" \
    --from-literal=INFLUX_URL="${DB_LORD_INFLUX_URL}" \
    --from-literal=INFLUX_ORG="${DB_LORD_INFLUX_ORG}" \
    --from-literal=INFLUX_BUCKET="${DB_LORD_INFLUX_BUCKET}" \
    --from-literal=INFLUX_TOKEN="${DB_LORD_INFLUX_TOKEN}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  echo "  - ${DB_LORD_NAMESPACE}/${DB_LORD_SECRET_NAME} (POSTGRES_*, INFLUX_*)"
fi

# Garmin is optional in the cloud-connector chart, so missing variables only skip
# this secret. kubectl apply only removes keys from its last applied configuration,
# so the secret's JWT_SECRET (not set with kubectl apply) is kept.
if [[ -n "${GARMIN_CLIENT_ID}" && -n "${GARMIN_CLIENT_SECRET}" ]]; then
  ensure_namespace "${CLOUD_CONNECTOR_NAMESPACE}"
  kubectl -n "${CLOUD_CONNECTOR_NAMESPACE}" create secret generic "${CLOUD_CONNECTOR_SECRET_NAME}" \
    --from-literal=GARMIN_CLIENT_ID="${GARMIN_CLIENT_ID}" \
    --from-literal=GARMIN_CLIENT_SECRET="${GARMIN_CLIENT_SECRET}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  echo "  - ${CLOUD_CONNECTOR_NAMESPACE}/${CLOUD_CONNECTOR_SECRET_NAME} (GARMIN_CLIENT_ID, GARMIN_CLIENT_SECRET)"
else
  echo "  - skipped ${CLOUD_CONNECTOR_NAMESPACE}/${CLOUD_CONNECTOR_SECRET_NAME} (GARMIN_CLIENT_ID and GARMIN_CLIENT_SECRET not set)"
fi
