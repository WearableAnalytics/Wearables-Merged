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

# --- helpers ---
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

# --- kafka (strimzi -> kafka -> topics -> mapper) ---
if ! helm status strimzi-cluster-operator -n kafka >/dev/null 2>&1; then
    cd "$APPS_DIR/platform"
	helm install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator --namespace kafka --create-namespace
fi

kubectl wait -n kafka deployment/strimzi-cluster-operator --for=condition=Available --timeout=300s

(
	cd "$APPS_DIR/platform"
	helm upgrade --install kafka ./kafka --values ./kafka/values.yaml --namespace kafka --create-namespace
)

sleep 10 #pod takes a little to be created, following command will fail if the pod doesnt exist
kubectl wait -n kafka pod/kafka-dual-role-0 --for=condition=Ready --timeout=600s

entity_operator_pod=""
for _ in {1..30}; do
	entity_operator_pod="$(kubectl get pods -n kafka -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep '^kafka-entity-operator-' | head -n1 || true)"
	if [[ -n "$entity_operator_pod" ]]; then
		break
	fi
	sleep 2
done

if [[ -z "$entity_operator_pod" ]]; then
	echo "Kafka entity operator pod not found in namespace kafka." >&2
	exit 1
fi

kubectl wait -n kafka pod/"$entity_operator_pod" --for=condition=Ready --timeout=300s


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

# --- influxdb + telegraf ---
(
	cd "$APPS_DIR/monitoring"
	helm upgrade --install influxdb ./influxdb --values ./influxdb/values.yaml --namespace influx --create-namespace
)

if lsof -iTCP:8086 -sTCP:LISTEN -Pn >/dev/null 2>&1; then
	if lsof -iTCP:8086 -sTCP:LISTEN -Pn; then #this assumes that its influx running on that port
		echo "InfluxDB port-forward already running on :8086"
	else
		echo "Port 8086 is already in use. Stop the process or choose a different port." >&2
		exit 1
	fi
else
	kubectl port-forward svc/influxdb-service -n influx 8086:8086 >/dev/null 2>&1 &
	sleep 1
fi

open http://localhost:8086

if [[ -z "${INFLUX_ORG:-}" || -z "${INFLUX_BUCKET:-}" || -z "${INFLUX_TOKEN:-}" ]]; then
	echo "InfluxDB setup requires manual steps to create org, bucket, and token." >&2
	echo "Open http://localhost:8086" >&2
	echo "INFLUX_ORG='${INFLUX_ORG-<unset>}' INFLUX_BUCKET='${INFLUX_BUCKET-<unset>}' INFLUX_TOKEN='${INFLUX_TOKEN-<unset>}'" >&2
	echo "Ensure the variables are exported in this shell. Run in the script directory" >&2
	echo "set -a" >&2
    echo "source .env" >&2
    echo "set +a" >&2
    echo "and then rerun the script" >&2
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

# --- ingress controller + shared ingress resources (CRDs) ---
(
	cd "$NETWORK_DIR"
	if ! helm status cert-manager -n cert-manager >/dev/null 2>&1; then
		helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager \
			--version v1.20.0 \
			--namespace cert-manager \
			--create-namespace \
			--set crds.enabled=true
	fi

	kubectl wait -n cert-manager deployment/cert-manager --for=condition=Available --timeout=300s
	kubectl wait -n cert-manager deployment/cert-manager-webhook --for=condition=Available --timeout=300s
	kubectl wait -n cert-manager deployment/cert-manager-cainjector --for=condition=Available --timeout=300s

	ingress_controller_args=(--values ./ingresscontroller/values.yaml)
	if [[ -n "${INGRESS_SERVICE_TYPE:-}" ]]; then
		ingress_controller_args+=(--set service.type="$INGRESS_SERVICE_TYPE")
	fi
	if [[ -n "${INGRESS_LB_IP:-}" ]]; then
		ingress_controller_args+=(--set service.lbIP="$INGRESS_LB_IP")
	fi
	if [[ -n "${INGRESS_LB_NETWORK_ID:-}" ]]; then
		ingress_controller_args+=(--set service.lbNetworkId="$INGRESS_LB_NETWORK_ID")
	fi
	if [[ -n "${INGRESS_LB_SUBNET_ID:-}" ]]; then
		ingress_controller_args+=(--set service.lbSubnetId="$INGRESS_LB_SUBNET_ID")
	fi
	if [[ -n "${INGRESS_WORKER_NODE_SUBNET_ID:-}" ]]; then
		ingress_controller_args+=(--set service.workerNodeSubnetId="$INGRESS_WORKER_NODE_SUBNET_ID")
	fi
	if [[ -n "${INGRESS_CLUSTER_ISSUER_NAME:-}" ]]; then
		ingress_controller_args+=(--set clusterIssuer.name="$INGRESS_CLUSTER_ISSUER_NAME")
	fi
	if [[ -n "${INGRESS_CLUSTER_ISSUER_SERVER:-}" ]]; then
		ingress_controller_args+=(--set clusterIssuer.acmeServer="$INGRESS_CLUSTER_ISSUER_SERVER")
	fi
	if [[ -n "${INGRESS_CLUSTER_ISSUER_EMAIL:-}" ]]; then
		ingress_controller_args+=(--set clusterIssuer.email="$INGRESS_CLUSTER_ISSUER_EMAIL")
	fi
	if [[ -n "${INGRESS_CLUSTER_ISSUER_SECRET_NAME:-}" ]]; then
		ingress_controller_args+=(--set clusterIssuer.privateKeySecretName="$INGRESS_CLUSTER_ISSUER_SECRET_NAME")
	fi
	if [[ -n "${INGRESS_CLUSTER_ISSUER_CLASS:-}" ]]; then
		ingress_controller_args+=(--set clusterIssuer.ingressClass="$INGRESS_CLUSTER_ISSUER_CLASS")
	fi

	helm upgrade --install traefik ./ingresscontroller "${ingress_controller_args[@]}" --namespace ingress --create-namespace
)

# Ensure Traefik CRDs exist before applying ingress resources
if ! kubectl get crd middlewares.traefik.io >/dev/null 2>&1; then
	kubectl apply -k "https://github.com/traefik/traefik-helm-chart/traefik/crds"
fi

# Wait for Traefik CRDs before applying ingress resources
required_crds=(middlewares.traefik.io serverstransports.traefik.io)
for crd in "${required_crds[@]}"; do
	for _ in {1..30}; do
		if kubectl get crd "$crd" >/dev/null 2>&1; then
			break
		fi
		sleep 2
		if [[ "$_" -eq 30 ]]; then
			echo "Traefik CRD not found: $crd" >&2
			exit 1
		fi
	done
done

(
	cd "$NETWORK_DIR"
	ingress_args=(--values ./ingress/values.yaml)
	if [[ -n "${INGRESS_HOST:-}" ]]; then
		ingress_args+=(--set ingress.host="$INGRESS_HOST")
	fi
	if [[ -n "${INGRESS_CERT_NAME:-}" ]]; then
		ingress_args+=(--set certificate.name="$INGRESS_CERT_NAME")
	fi
	if [[ -n "${INGRESS_CERT_SECRET_NAME:-}" ]]; then
		ingress_args+=(--set certificate.secretName="$INGRESS_CERT_SECRET_NAME")
	fi

	helm upgrade --install traefik-ingress ./ingress "${ingress_args[@]}" --namespace ingress --create-namespace
)

# --- importservice + grafana ---
(
	cd "$APPS_DIR/services"
	helm upgrade --install importservice ./importservice --values ./importservice/values.yaml --namespace importservice --create-namespace
)

(
	cd "$APPS_DIR/monitoring"
	helm upgrade --install grafana ./grafana --values ./grafana/values.yaml --namespace grafana --create-namespace
)

# --- prod-postgres ---

require_env PROD_POSTGRES_PASSWORD
require_env PROD_POSTGRES_DBLORD_PASSWORD
require_env PROD_POSTGRES_LAKEFS_PASSWORD

(
	cd "$APPS_DIR/platform"
	helm upgrade --install prod-postgres ./prod-postgres --values ./prod-postgres/values.yaml --namespace "$PROD_POSTGRES_NAMESPACE" --create-namespace \
		--set-string auth.postgresPassword="$PROD_POSTGRES_PASSWORD"\
		--set-string databases[0].password="$PROD_POSTGRES_DBLORD_PASSWORD" \
		--set-string databases[1].password="$PROD_POSTGRES_LAKEFS_PASSWORD"
)

# --- db-lord ---
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

db_lord_secret_file="$(mktemp)"
db_lord_job_file="$(mktemp)"

helm template db-lord "$APPS_DIR/services/db-lord" --namespace "$DB_LORD_NAMESPACE" \
	--set env.POSTGRES_SERVER="$DB_LORD_POSTGRES_SERVER" \
	--set env.POSTGRES_PORT="$DB_LORD_POSTGRES_PORT" \
	--set env.POSTGRES_DB="$DB_LORD_POSTGRES_DB" \
	--set env.POSTGRES_USER="$DB_LORD_POSTGRES_USER" \
	--set env.POSTGRES_PASSWORD="$DB_LORD_POSTGRES_PASSWORD" \
	--set env.INFLUX_URL="$DB_LORD_INFLUX_URL" \
	--set env.INFLUX_ORG="$DB_LORD_INFLUX_ORG" \
	--set env.INFLUX_BUCKET="$DB_LORD_INFLUX_BUCKET" \
	--set env.INFLUX_TOKEN="$DB_LORD_INFLUX_TOKEN" \
	-s templates/db-lord-secrets.yaml >"$db_lord_secret_file"

kubectl apply -f "$db_lord_secret_file" -n "$DB_LORD_NAMESPACE" >/dev/null

kubectl -n "$DB_LORD_NAMESPACE" label secret "$DB_LORD_SECRET_NAME" \
	app.kubernetes.io/managed-by=Helm --overwrite >/dev/null

kubectl -n "$DB_LORD_NAMESPACE" annotate secret "$DB_LORD_SECRET_NAME" \
	meta.helm.sh/release-name=db-lord \
	meta.helm.sh/release-namespace="$DB_LORD_NAMESPACE" \
	--overwrite >/dev/null

helm template db-lord "$APPS_DIR/services/db-lord" --namespace "$DB_LORD_NAMESPACE" \
	--set env.POSTGRES_SERVER="$DB_LORD_POSTGRES_SERVER" \
	--set env.POSTGRES_PORT="$DB_LORD_POSTGRES_PORT" \
	--set env.POSTGRES_DB="$DB_LORD_POSTGRES_DB" \
	--set env.POSTGRES_USER="$DB_LORD_POSTGRES_USER" \
	--set env.POSTGRES_PASSWORD="$DB_LORD_POSTGRES_PASSWORD" \
	-s templates/job-migrate.yaml >"$db_lord_job_file"

kubectl delete job db-lord-migrate -n "$DB_LORD_NAMESPACE" --ignore-not-found
kubectl apply -f "$db_lord_job_file" -n "$DB_LORD_NAMESPACE"

helm upgrade --install db-lord "$APPS_DIR/services/db-lord" --namespace "$DB_LORD_NAMESPACE"

rm -f "$db_lord_secret_file" "$db_lord_job_file"

# --- extraction-service ---
ensure_namespace "$EXTRACTION_SERVICE_NAMESPACE"
require_env EXTRACTION_SERVICE_DB_LORD_BASE_URL

kubectl -n "$EXTRACTION_SERVICE_NAMESPACE" create secret generic "$EXTRACTION_SERVICE_SECRET_NAME" \
	--from-literal=DB_LORD_BASE_URL="$EXTRACTION_SERVICE_DB_LORD_BASE_URL" \
	--dry-run=client -o yaml | kubectl apply -f - >/dev/null

helm upgrade --install extraction-service "$APPS_DIR/services/extraction-service" --namespace "$EXTRACTION_SERVICE_NAMESPACE" --create-namespace \
	--set env.DB_LORD_BASE_URL="$EXTRACTION_SERVICE_DB_LORD_BASE_URL"

# --- runtime secrets + bff/grafana-proxy/frontend ---
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