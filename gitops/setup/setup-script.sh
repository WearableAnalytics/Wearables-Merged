#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITOPS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APPS_DIR="$GITOPS_DIR/apps"
NETWORK_DIR="$GITOPS_DIR/network"

BFF_NAMESPACE="${BFF_NAMESPACE:-wearables-bff}"
BFF_SECRET_NAME="${BFF_SECRET_NAME:-wearables-bff-secrets}"
BFF_FRONTEND_ORIGINS="${BFF_FRONTEND_ORIGINS:-http://wearables.charite.de/}"
BFF_FRONTEND_REDIRECT_URL="${BFF_FRONTEND_REDIRECT_URL:-http://wearables.charite.de/}"
BFF_ADMIN_EMAILS="${BFF_ADMIN_EMAILS:-linus.gustafsson@tu-berlin.de,j.moehler@posteo.de,admin@lukaszsztukiewicz.com,gmsdaniilplay@gmail.com}"
BFF_USE_MOCK_DATA="${BFF_USE_MOCK_DATA:-false}"
BFF_DATABASE_API_URL="${BFF_DATABASE_API_URL:-http://db-lord.db-lord.svc.cluster.local:8080}"
BFF_DATABASE_API_TIMEOUT="${BFF_DATABASE_API_TIMEOUT:-30000}"
PUBLIC_API_BASE_URL="${PUBLIC_API_BASE_URL:-http://wearables.charite.de}"
GRAFANA_NAMESPACE="${GRAFANA_NAMESPACE:-monitoring}"
GRAFANA_SECRET_NAME="${GRAFANA_SECRET_NAME:-grafana-auth-secrets}"
GRAFANA_JWT_PRIVATE_KEY_PATH="${GRAFANA_JWT_PRIVATE_KEY_PATH:-$REPO_ROOT/secrets/grafana-jwt-private.pem}"

PROD_POSTGRES_NAMESPACE="${PROD_POSTGRES_NAMESPACE:-prod-postgres}"

DB_LORD_NAMESPACE="${DB_LORD_NAMESPACE:-db-lord}"

EXTRACTION_SERVICE_NAMESPACE="${EXTRACTION_SERVICE_NAMESPACE:-extraction-service}"
INGRESS_HTTP_ONLY="${INGRESS_HTTP_ONLY:-false}"
GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"
GRAFANA_SUBPATH="${GRAFANA_SUBPATH:-/grafana}"

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

configure_grafana_datasources() {
	local grafana_namespace="grafana"
	local grafana_service_name="grafana"
	local influx_datasource_name="InfluxDB"
	local prometheus_datasource_name="Prometheus"

	echo "Waiting for Grafana deployment to become ready..."
	kubectl wait -n "$grafana_namespace" deployment/"$grafana_service_name" --for=condition=Available --timeout=300s

	echo "Configuring Grafana datasources via API..."
	kubectl -n "$grafana_namespace" run grafana-datasource-bootstrap --rm -i --restart=Never \
		--image=curlimages/curl:8.8.0 \
		--env="INFLUX_ORG=$INFLUX_ORG" \
		--env="INFLUX_BUCKET=$INFLUX_BUCKET" \
		--env="INFLUX_TOKEN=$INFLUX_TOKEN" \
		--env="GRAFANA_ADMIN_USER=$GRAFANA_ADMIN_USER" \
		--env="GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD" \
		--env="GRAFANA_SUBPATH=$GRAFANA_SUBPATH" \
		--env="INFLUX_DATASOURCE_NAME=$influx_datasource_name" \
		--env="PROMETHEUS_DATASOURCE_NAME=$prometheus_datasource_name" \
		--command -- sh -ceu '
			subpath="${GRAFANA_SUBPATH%/}"
			if [[ "$subpath" == "/" ]]; then
				subpath=""
			fi
			api_base="http://grafana:3000${subpath}/api"
			login_url="http://grafana:3000${subpath}/login"
			cookie_jar="/tmp/grafana-cookies.txt"

			cat > /tmp/influx-datasource.json <<JSON
{
	"name": "${INFLUX_DATASOURCE_NAME}",
  "type": "influxdb",
  "access": "proxy",
  "url": "http://influxdb-service.influx.svc.cluster.local:8086",
  "database": "${INFLUX_BUCKET}",
  "user": "${INFLUX_ORG}",
  "basicAuth": true,
  "basicAuthUser": "${INFLUX_ORG}",
  "isDefault": true,
  "jsonData": {
    "httpMode": "POST"
  },
  "secureJsonData": {
    "basicAuthPassword": "${INFLUX_TOKEN}"
  }
}
JSON

			cat > /tmp/prometheus-datasource.json <<JSON
{
	"name": "${PROMETHEUS_DATASOURCE_NAME}",
	"type": "prometheus",
	"access": "proxy",
	"url": "http://prometheus-service.monitoring.svc.cluster.local",
	"isDefault": false,
	"jsonData": {
		"httpMethod": "POST"
	}
}
JSON

			login_status="$(curl -sS -L --post301 --post302 --post303 -o /tmp/login-response.json -w "%{http_code}" \
				-c "$cookie_jar" \
				-H "Content-Type: application/json" \
				-X POST "$login_url" \
				--data "{\"user\":\"${GRAFANA_ADMIN_USER}\",\"password\":\"${GRAFANA_ADMIN_PASSWORD}\"}")"

			if [[ "$login_status" != "200" && "$login_status" != "204" ]]; then
				echo "Grafana login failed (HTTP $login_status)." >&2
				cat /tmp/login-response.json >&2
				exit 1
			fi

			if ! grep -q "grafana_session" "$cookie_jar"; then
				echo "Grafana login did not return a session cookie." >&2
				echo "Check GRAFANA_ADMIN_USER/GRAFANA_ADMIN_PASSWORD and GRAFANA_SUBPATH (${GRAFANA_SUBPATH})." >&2
				exit 1
			fi

			upsert_datasource() {
				local ds_name="$1"
				local ds_file="$2"

				curl -sS -b "$cookie_jar" -X DELETE "$api_base/datasources/name/${ds_name}" >/dev/null || true

				status="$(curl -sS -o /tmp/response.json -w "%{http_code}" -b "$cookie_jar" \
					-H "Content-Type: application/json" \
					-X POST "$api_base/datasources" \
					--data @"$ds_file")"

				if [[ "$status" == "200" || "$status" == "201" ]]; then
					echo "Configured datasource: $ds_name"
					return 0
				fi

				echo "Failed to configure datasource $ds_name (HTTP $status)." >&2
				cat /tmp/response.json >&2
				return 1
			}

			upsert_datasource "$INFLUX_DATASOURCE_NAME" /tmp/influx-datasource.json
			upsert_datasource "$PROMETHEUS_DATASOURCE_NAME" /tmp/prometheus-datasource.json

			echo "Grafana datasources configured successfully."
		'
}

kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml

kubectl wait -n local-path-storage deployment/local-path-provisioner --for=condition=Available --timeout=300s

echo "installed local path provisioner"

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
	ingress_args+=(--set ingress.httpOnly="$INGRESS_HTTP_ONLY")
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
	helm upgrade --install importservice ./importservice --values ./importservice/values.yaml --namespace importservice --create-namespace \
		--set ingress.httpOnly="$INGRESS_HTTP_ONLY"
)

(
	cd "$APPS_DIR/monitoring"
	helm upgrade --install grafana ./grafana --values ./grafana/values.yaml --namespace grafana --create-namespace \
		--set ingress.httpOnly="$INGRESS_HTTP_ONLY"
)

(
	cd "$APPS_DIR/monitoring"
	helm upgrade --install prometheus ./prometheus --values ./prometheus/values.yaml --namespace monitoring --create-namespace
)

configure_grafana_datasources

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
require_env DB_LORD_POSTGRES_SERVER
require_env DB_LORD_POSTGRES_PORT
require_env DB_LORD_POSTGRES_DB
require_env DB_LORD_POSTGRES_USER
require_env DB_LORD_POSTGRES_PASSWORD
require_env DB_LORD_INFLUX_URL


helm upgrade --install db-lord "$APPS_DIR/services/db-lord" \
	--namespace "$DB_LORD_NAMESPACE" \
	--create-namespace \
	--set env.POSTGRES_SERVER="$DB_LORD_POSTGRES_SERVER" \
	--set env.POSTGRES_PORT="$DB_LORD_POSTGRES_PORT" \
	--set env.POSTGRES_DB="$DB_LORD_POSTGRES_DB" \
	--set env.POSTGRES_USER="$DB_LORD_POSTGRES_USER" \
	--set env.POSTGRES_PASSWORD="$DB_LORD_POSTGRES_PASSWORD" \
	--set env.INFLUX_URL="$DB_LORD_INFLUX_URL" \
	--set env.INFLUX_ORG="$INFLUX_ORG" \
	--set env.INFLUX_BUCKET="$INFLUX_BUCKET" \
	--set env.INFLUX_TOKEN="$INFLUX_TOKEN"

# --- extraction-service ---
require_env EXTRACTION_SERVICE_DB_LORD_BASE_URL

helm upgrade --install extraction-service "$APPS_DIR/services/extraction-service" --namespace "$EXTRACTION_SERVICE_NAMESPACE" --create-namespace \
	--set env.DB_LORD_BASE_URL="$EXTRACTION_SERVICE_DB_LORD_BASE_URL"

# --- runtime secrets + bff/grafana-proxy/frontend ---
bash "$REPO_ROOT/scripts/bootstrap-runtime-secrets.sh"

echo "Successfully executed bootrap script"

require_file "$GRAFANA_JWT_PRIVATE_KEY_PATH"

BFF_ADMIN_EMAILS_HELM_ESCAPED="${BFF_ADMIN_EMAILS//,/\\,}"

helm upgrade --install wearables-bff "$APPS_DIR/services/wearables-bff" \
	--namespace "$BFF_NAMESPACE" \
	--create-namespace \
	--set secret.create=false \
	--set secret.name="$BFF_SECRET_NAME" \
	--set-string env.USE_MOCK_DATA="$BFF_USE_MOCK_DATA" \
	--set-string env.DATABASE_API_URL="$BFF_DATABASE_API_URL" \
	--set-string env.DATABASE_API_TIMEOUT="$BFF_DATABASE_API_TIMEOUT" \
	--set-string env.BACKEND_URL="$PUBLIC_API_BASE_URL" \
	--set-string env.FRONTEND_ORIGINS="$BFF_FRONTEND_ORIGINS" \
	--set-string env.FRONTEND_REDIRECT_URL="$BFF_FRONTEND_REDIRECT_URL" \
	--set-string env.ADMIN_EMAILS="$BFF_ADMIN_EMAILS_HELM_ESCAPED" \
	--set ingress.httpOnly="$INGRESS_HTTP_ONLY" \
	-f "$APPS_DIR/services/wearables-bff/values.yaml"

helm upgrade --install grafana-proxy "$APPS_DIR/monitoring/grafana-proxy" \
	-n "$GRAFANA_NAMESPACE" \
	--create-namespace \
	--set secret.name="$GRAFANA_SECRET_NAME" \
	--set ingress.httpOnly="$INGRESS_HTTP_ONLY" \
	-f "$APPS_DIR/monitoring/grafana-proxy/values.yaml"

helm upgrade --install web "$APPS_DIR/web-frontend" \
	-n web \
	--create-namespace \
	--set-string runtimeConfig.apiBaseUrl="$PUBLIC_API_BASE_URL/api" \
	--set ingress.httpOnly="$INGRESS_HTTP_ONLY" \
	-f "$APPS_DIR/web-frontend/values.yaml"