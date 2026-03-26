#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITOPS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APPS_DIR="$GITOPS_DIR/apps"
NETWORK_DIR="$GITOPS_DIR/network"

BFF_NAMESPACE="${BFF_NAMESPACE:-wearables-bff}"
BFF_SECRET_NAME="${BFF_SECRET_NAME:-wearables-bff-secrets}"
GRAFANA_NAMESPACE="${GRAFANA_NAMESPACE:-monitoring}"
GRAFANA_SECRET_NAME="${GRAFANA_SECRET_NAME:-grafana-auth-secrets}"
GRAFANA_JWT_PRIVATE_KEY_PATH="${GRAFANA_JWT_PRIVATE_KEY_PATH:-$REPO_ROOT/secrets/grafana-jwt-private.pem}"

PROD_POSTGRES_NAMESPACE="${PROD_POSTGRES_NAMESPACE:-prod-postgres}"

DB_LORD_NAMESPACE="${DB_LORD_NAMESPACE:-db-lord}"
DB_LORD_SECRET_NAME="${DB_LORD_SECRET_NAME:-db-lord-secrets}"

EXTRACTION_SERVICE_NAMESPACE="${EXTRACTION_SERVICE_NAMESPACE:-extraction-service}"
EXTRACTION_SERVICE_SECRET_NAME="${EXTRACTION_SERVICE_SECRET_NAME:-extraction-service-secrets}"

if ! command -v helm >/dev/null 2>&1; then
	echo "helm is required but not installed."
	exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
	echo "kubectl is required but not installed."
	exit 1
fi

ensure_namespace() {
	local namespace="$1"
	if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
		kubectl create namespace "$namespace" >/dev/null
	fi
}

require_env() {
	local var_name="$1"
	if [[ -z "${!var_name:-}" ]]; then
		echo "Missing required env var: ${var_name}" >&2
		exit 1
	fi
}

require_file() {
	local file_path="$1"
	if [[ ! -f "$file_path" ]]; then
		echo "Missing required file: ${file_path}" >&2
		exit 1
	fi
}

if ! helm status strimzi-cluster-operator -n kafka >/dev/null 2>&1; then
    cd "$APPS_DIR/platform"
	helm install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator --values ./strimzi/values.yaml --namespace kafka --create-namespace
fi

(
	cd "$APPS_DIR/platform"
	helm upgrade --install kafka ./kafka --values ./kafka/values.yaml --namespace kafka --create-namespace
)

if [[ -n "${KAFKA_TOPICS:-}" ]]; then
	IFS="," read -r -a TOPICS <<< "$KAFKA_TOPICS"
	for topic in "${TOPICS[@]}"; do
		topic_trimmed="$(echo "$topic" | xargs)"
		if [[ -n "$topic_trimmed" ]]; then
			kubectl exec -n kafka kafka-dual-role-0 -- bin/kafka-topics.sh --create --topic "$topic_trimmed" --bootstrap-server localhost:9092 --partitions "${KAFKA_PARTITIONS:-1}" --if-not-exists
		fi
	done
else
	echo "Set KAFKA_TOPICS as a comma-separated list to create topics automatically."
	echo "Example: KAFKA_TOPICS=wearables-lp,wearables-fhir"
fi

(
	cd "$APPS_DIR/services"
	helm upgrade --install mapper-validator ./mapper-validator --values ./mapper-validator/values.yaml --namespace kafka --create-namespace
)

(
	cd "$APPS_DIR/monitoring"
	helm upgrade --install influxdb ./influxdb --values ./influxdb/values.yaml --namespace influx --create-namespace
)

if [[ -z "${INFLUX_ORG:-}" || -z "${INFLUX_BUCKET:-}" || -z "${INFLUX_TOKEN:-}" ]]; then
	echo "InfluxDB setup requires manual steps to create org, bucket, and token." >&2
	echo "Set INFLUX_ORG, INFLUX_BUCKET, and INFLUX_TOKEN, then re-run this script." >&2
	exit 1
else
	(
		cd "$APPS_DIR/monitoring"
		helm upgrade --install telegraf ./telegraf --values ./telegraf/values.yaml --namespace telegraf \
			--create-namespace \
			--set config.influxProducer.org="$INFLUX_ORG" \
			--set config.influxProducer.bucket="$INFLUX_BUCKET" \
			--set config.influxProducer.token="$INFLUX_TOKEN"
	)
fi

(
	cd "$APPS_DIR/services"
	helm upgrade --install importservice ./importservice --values ./importservice/values.yaml --namespace importservice --create-namespace
)

(
	cd "$APPS_DIR/monitoring"
	helm upgrade --install grafana ./grafana --values ./grafana/values.yaml --namespace grafana --create-namespace
)

require_env PROD_POSTGRES_PASSWORD
require_env PROD_POSTGRES_INFISICAL_PASSWORD
require_env PROD_POSTGRES_DBLORD_PASSWORD
require_env PROD_POSTGRES_LAKEFS_PASSWORD

(
	cd "$APPS_DIR/platform"
	helm upgrade --install prod-postgres ./prod-postgres --values ./prod-postgres/values.yaml --namespace "$PROD_POSTGRES_NAMESPACE" --create-namespace \
		--set-string auth.postgresPassword="$PROD_POSTGRES_PASSWORD" \
		--set-string databases[0].password="$PROD_POSTGRES_INFISICAL_PASSWORD" \
		--set-string databases[1].password="$PROD_POSTGRES_DBLORD_PASSWORD" \
		--set-string databases[2].password="$PROD_POSTGRES_LAKEFS_PASSWORD"
)

ensure_namespace "$DB_LORD_NAMESPACE"
require_env DB_LORD_POSTGRES_SERVER
require_env DB_LORD_POSTGRES_PORT
require_env DB_LORD_POSTGRES_DB
require_env DB_LORD_POSTGRES_USER
require_env DB_LORD_POSTGRES_PASSWORD
require_env DB_LORD_INFLUX_URL
require_env DB_LORD_INFLUX_ORG
require_env DB_LORD_INFLUX_BUCKET
require_env DB_LORD_INFLUX_TOKEN

kubectl -n "$DB_LORD_NAMESPACE" create secret generic "$DB_LORD_SECRET_NAME" \
	--from-literal=POSTGRES_SERVER="$DB_LORD_POSTGRES_SERVER" \
	--from-literal=POSTGRES_PORT="$DB_LORD_POSTGRES_PORT" \
	--from-literal=POSTGRES_DB="$DB_LORD_POSTGRES_DB" \
	--from-literal=POSTGRES_USER="$DB_LORD_POSTGRES_USER" \
	--from-literal=POSTGRES_PASSWORD="$DB_LORD_POSTGRES_PASSWORD" \
	--from-literal=INFLUX_URL="$DB_LORD_INFLUX_URL" \
	--from-literal=INFLUX_ORG="$DB_LORD_INFLUX_ORG" \
	--from-literal=INFLUX_BUCKET="$DB_LORD_INFLUX_BUCKET" \
	--from-literal=INFLUX_TOKEN="$DB_LORD_INFLUX_TOKEN" \
	--dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl delete job db-lord-migrate -n "$DB_LORD_NAMESPACE" --ignore-not-found
helm template db-lord "$APPS_DIR/services/db-lord" --namespace "$DB_LORD_NAMESPACE" -s templates/job-migrate.yaml | kubectl apply -n "$DB_LORD_NAMESPACE" -f -

helm upgrade --install db-lord "$APPS_DIR/services/db-lord" --namespace "$DB_LORD_NAMESPACE" \
	--set env.POSTGRES_SERVER="$DB_LORD_POSTGRES_SERVER" \
	--set env.POSTGRES_PORT="$DB_LORD_POSTGRES_PORT" \
	--set env.POSTGRES_DB="$DB_LORD_POSTGRES_DB" \
	--set env.POSTGRES_USER="$DB_LORD_POSTGRES_USER" \
	--set env.POSTGRES_PASSWORD="$DB_LORD_POSTGRES_PASSWORD" \
	--set env.INFLUX_URL="$DB_LORD_INFLUX_URL" \
	--set env.INFLUX_ORG="$DB_LORD_INFLUX_ORG" \
	--set env.INFLUX_BUCKET="$DB_LORD_INFLUX_BUCKET" \
	--set env.INFLUX_TOKEN="$DB_LORD_INFLUX_TOKEN"

ensure_namespace "$EXTRACTION_SERVICE_NAMESPACE"
require_env EXTRACTION_SERVICE_DB_LORD_BASE_URL

kubectl -n "$EXTRACTION_SERVICE_NAMESPACE" create secret generic "$EXTRACTION_SERVICE_SECRET_NAME" \
	--from-literal=DB_LORD_BASE_URL="$EXTRACTION_SERVICE_DB_LORD_BASE_URL" \
	--dry-run=client -o yaml | kubectl apply -f - >/dev/null

helm upgrade --install extraction-service "$APPS_DIR/services/extraction-service" --namespace "$EXTRACTION_SERVICE_NAMESPACE" --create-namespace \
	--set env.DB_LORD_BASE_URL="$EXTRACTION_SERVICE_DB_LORD_BASE_URL"

require_env RESEARCHER_API_ACCESS_TOKEN
require_file "$GRAFANA_JWT_PRIVATE_KEY_PATH"

bash "$REPO_ROOT/scripts/bootstrap-runtime-secrets.sh"

helm upgrade --install wearables-bff "$APPS_DIR/services/wearables-bff" \
	--namespace "$BFF_NAMESPACE" \
	--create-namespace \
	--set secret.create=false \
	--set secret.name="$BFF_SECRET_NAME" \
	-f "$APPS_DIR/services/wearables-bff/values.yaml"

helm upgrade --install grafana-proxy "$APPS_DIR/monitoring/grafana-proxy" \
	-n "$GRAFANA_NAMESPACE" \
	--create-namespace \
	--set secret.name="$GRAFANA_SECRET_NAME" \
	-f "$APPS_DIR/monitoring/grafana-proxy/values.yaml"

helm upgrade --install web "$APPS_DIR/web-frontend" \
	-n web \
	--create-namespace \
	-f "$APPS_DIR/web-frontend/values.yaml"

(
	cd "$NETWORK_DIR/ingresscontroller"
	helm upgrade --install traefik ./ingresscontroller --values ./ingresscontroller/values.yaml --namespace ingress --create-namespace
)

(
	cd "$NETWORK_DIR/ingress"
	helm upgrade --install traefik-ingress ./ingress --values ./ingress/values.yaml --namespace ingress --create-namespace
)