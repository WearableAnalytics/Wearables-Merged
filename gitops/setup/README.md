# Setup Environment Variables

This directory contains environment files used by the setup script.

## Usage

1. Copy .env.example to .env and fill in the values.
2. Export variables before running the script:

   set -a
   source .env
   set +a
   bash ./setup-script.sh

## Variables

### Kafka topics (optional)
- KAFKA_TOPICS: Comma-separated list of Kafka topics to create. Leave empty to skip.
- KAFKA_PARTITIONS: Partition count for created topics. Default is 1.

### InfluxDB / Telegraf (required to install Telegraf)
- INFLUX_ORG: Influx org name used by Telegraf.
- INFLUX_BUCKET: Influx bucket name used by Telegraf.
- INFLUX_TOKEN: Influx token used by Telegraf.

These are required to proceed past the Telegraf step.

### prod-postgres secrets (required)
- PROD_POSTGRES_PASSWORD: Password for the main postgres user.
- PROD_POSTGRES_INFISICAL_PASSWORD: Password for the infisical database user.
- PROD_POSTGRES_DBLORD_PASSWORD: Password for the db-lord database user.
- PROD_POSTGRES_LAKEFS_PASSWORD: Password for the lakefs database user.
- PROD_POSTGRES_NAMESPACE: Namespace for prod-postgres. Default is prod-postgres.

### db-lord secrets (required)
- DB_LORD_POSTGRES_SERVER: Postgres host for db-lord.
- DB_LORD_POSTGRES_PORT: Postgres port for db-lord.
- DB_LORD_POSTGRES_DB: Postgres database name for db-lord.
- DB_LORD_POSTGRES_USER: Postgres user for db-lord.
- DB_LORD_POSTGRES_PASSWORD: Postgres password for db-lord.
- DB_LORD_INFLUX_URL: Influx base URL for db-lord.
- DB_LORD_INFLUX_ORG: Influx org for db-lord.
- DB_LORD_INFLUX_BUCKET: Influx bucket for db-lord.
- DB_LORD_INFLUX_TOKEN: Influx token for db-lord.
- DB_LORD_NAMESPACE: Namespace for db-lord. Default is db-lord.
- DB_LORD_SECRET_NAME: Secret name for db-lord. Default is db-lord-secrets.

### extraction-service secrets (required)
- EXTRACTION_SERVICE_DB_LORD_BASE_URL: Base URL for db-lord used by extraction-service.
- EXTRACTION_SERVICE_NAMESPACE: Namespace for extraction-service. Default is extraction-service.
- EXTRACTION_SERVICE_SECRET_NAME: Secret name for extraction-service. Default is extraction-service-secrets.

### runtime secret bootstrap (required)
- RESEARCHER_API_ACCESS_TOKEN: Required API access token for wearables-bff.
- BREVO_API_KEY: Optional unless NODE_ENV is production.
- GRAFANA_JWT_PRIVATE_KEY_PATH: Path to the Grafana private key file.
- SHARED_APP_JWT_SECRET: Optional override for the shared JWT secret.
- ROTATE_SHARED_APP_JWT_SECRET: Set true to force a new shared JWT secret.
- BFF_NAMESPACE: Namespace for wearables-bff. Default is wearables-bff.
- BFF_SECRET_NAME: Secret name for wearables-bff. Default is wearables-bff-secrets.
- GRAFANA_NAMESPACE: Namespace for grafana-proxy. Default is monitoring.
- GRAFANA_SECRET_NAME: Secret name for grafana-proxy. Default is grafana-auth-secrets.

### ingress controller (optional)
For local/minikube, leave these empty. For external load balancers, set as needed.

- INGRESS_SERVICE_TYPE: Service type, e.g., LoadBalancer or NodePort.
- INGRESS_LB_IP: Explicit load balancer IP, if applicable.
- INGRESS_LB_NETWORK_ID: Provider-specific network id.
- INGRESS_LB_SUBNET_ID: Provider-specific subnet id.
- INGRESS_WORKER_NODE_SUBNET_ID: Provider-specific worker subnet id.

### cluster issuer (optional)
Leave empty if you do not want cert-manager to create a ClusterIssuer.

- INGRESS_CLUSTER_ISSUER_NAME: ClusterIssuer name.
- INGRESS_CLUSTER_ISSUER_SERVER: ACME server URL.
- INGRESS_CLUSTER_ISSUER_EMAIL: Contact email for ACME account.
- INGRESS_CLUSTER_ISSUER_SECRET_NAME: Secret name for the ACME account key.
- INGRESS_CLUSTER_ISSUER_CLASS: Ingress class used for ACME challenges.

### ingress (optional)
Leave empty to skip domain-specific certificates.

- INGRESS_HOST: Domain name for certificates.
- INGRESS_CERT_NAME: Certificate resource name.
- INGRESS_CERT_SECRET_NAME: Secret name where the certificate is stored.
