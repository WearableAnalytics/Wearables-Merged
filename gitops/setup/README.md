# Setup for the Wearables Project

This directory contains scripts and environment variables that are needed to set up the Wearables Platform in a few clicks.

# Prerequisites

- Helm (v4.1.3)
- kubectl (v1.35.3)
- Minikube (v1.38.1)
- k9s (recommended for ease of use)
- min. 4 cores + 16GB RAM preferable

**Notes:**
- this guide was only tested on Mac (MacOS 15.7.4 (24G517))
   - it uses some tools that are only available on MacOS (other OS users must find alternatives)
- this guide is made to be used with a remote minikibe cluster (controlled via ssh)
   - if not running on minikube, things may have to be changed (e.g. storage classes, networking settings etc.)
   - you must have sudo rights on the machine hosting the cluster
- images must be built for the correct architecture (here x86-64)
- the system was built to be publicly reachable from a domain. To work around this dependency we had to "hack" a little
- the guide describes how to use the system with traefik acting as a NodePort instead of a (publicly exposed) LoadBalancer
- the BFF integration with the db-lord unfortunately broke in the final steps of the project and we did not have time to fix it. Hence to still provide the shown functionality, bff is running with fake data. This can be customized using .env vars.
- If there is an issue during setup with an unclear rigin and it can not be resolved. Try purging minikube and restarting the deployment

## Usage

In the following we will walk through the steps of how to use this script.

1. Create a VM and enable a ssh connection to it with the following config

```bash
Host dsp-test
  HostName xxx.xxx.xxx.xxx #(IP)
  IdentityFile ~/.ssh/your_identity_file
  User your_user
  LocalForward 8086 localhost:8086 #needed for setup
  LocalForward 127.0.0.1:12345 wearables.charite.de:XXXXX #needed for browser interaction
  # Note: XXXXXX above needs to be replaced in later step
```

2. Clone the repo onto the VM (recommended) or take additional measures to use local kubectl.
3. Start a 3 node minikube deployment: `minikube start -n 3`
3. Navigate to `Wearables-Merged/gitops/setup`
4. Copy .env.example to .env and fill in the values (we may have provided them to you); functionality can only be guaranteed for these values 
5. Add a valid email from you to `BFF_ADMIN_EMAILS`
5. Export variables before running the script:

```bash
   set -a
   source .env
   set +a
   bash ./setup-script.sh
```

6. The script will now run until Influx is set up and then stop as manual measures need to be taken. 
7. Port forward the influxdb service to localhost:8086. Open `localhost:8086` in your browser (see ssh port-forwards)
8. Fill all fields and remember the values. Click continue and copy the token presented to you.
9. Set the token as `INFLUX_TOKEN` and `INFLUX_ORG` and `INFLUX_BUCKET` as the values you set in the previous step. Bucket refers to the database.
10. Source the .env again (see above) and execute the script again.
11. Everyhting should be deployed this time. 

### Access Grafana

1. Check the NodePorts of traefik. Find the plain http port (web) and enter it in the ssh config, where we previously did not enter anyhting.
2. Restart the ssh connection
3. Switch into sudo mode on the VM and edit the `/etc/hosts` file
4. Find the minikube Ip with `minikube ip` and append the following entry and save the file.

```bash
192.168.58.2  wearables.charite.de #replace the IP with the minikube IP on your machine if it is different.
```
5. Open the `/etc/hosts` file on your Mac and append the following entry and save. We need to do this as the Host must be the one defined in the cluster and we cannot use only IP adresses. This will foward all requests in made to the domain in plain HTTP to localhost, which will be forwarded via SSH to the same domain and then to k8s.

```bash
127.0.0.1 wearables.charite.de
```

6. As the browser can only make real HTTP calls to port 80 without specifying a port explicitly we need to make another change. This is only available on Mac. If you have a non-standard `pf.conf` save it and run the following commands.

```bash
echo "rdr pass on lo0 inet proto tcp from any to 127.0.0.1 port 80 -> 127.0.0.1 port 12345" | sudo pfctl -ef -

echo "rdr pass on lo0 proto tcp from any to any port 80 -> 127.0.0.1 port 12345" | sudo pfctl -ef -
```

This will transparently forward all calls to 80. To restore run `sudo pfctl -ef /etc/pf.conf` and turn off if not previously running with `sudo pfctl -d`

7. Open the browser to http://wearables.charite.de/grafana. This should now forward to the clusters grafana instance. Ensure you are not using HTTPS.
8. If not logged in, log in now with the credentials specified in the `.env`. Grafana sources are automatically configured for prometheus and InfluxDB. Dashboards can be imported from `/observability/dashboards`. One is for the ML insights, one for the regular measurements and one for Kafka observability.
9. Open `http://wearables.charite.de`. You should be prompted to insert an Email. Enter the one you added to the admin emails above and press the arrow.
10. You should have received a mail. Click on the link. You should be forwared to the Clincians Overview where you can see current cases (will be empty now) and add new cases.
11. TODO

## Variables

### Storage
- STORAGE_CLASS: StorageClass for all stateful charts. Default is `cinder-csi` (de.NBI/Kubermatic). Use `local-path` on minikube or k3s; the script then installs the local-path provisioner. See [docs/storage-concept.md](../../docs/storage-concept.md).

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
- BREVO_API_KEY: Optional unless NODE_ENV is production.
- GRAFANA_JWT_PRIVATE_KEY_PATH: Path to the Grafana private key file.
- SHARED_APP_JWT_SECRET: Optional override for the shared JWT secret.
- ROTATE_SHARED_APP_JWT_SECRET: Set true to force a new shared JWT secret.
- BFF_NAMESPACE: Namespace for wearables-bff. Default is wearables-bff.
- BFF_SECRET_NAME: Secret name for wearables-bff. Default is wearables-bff-secrets.
- BFF_FRONTEND_ORIGINS: Comma-separated CORS origins for wearables-bff. Default is http://wearables.charite.de/.
- BFF_FRONTEND_REDIRECT_URL: Frontend redirect URL for wearables-bff links. Default is http://wearables.charite.de/.
- BFF_ADMIN_EMAILS: Comma-separated admin emails passed to wearables-bff `ADMIN_EMAILS`. Default is the maintainers list in `gitops/setup/.env.example`.
- BFF_USE_MOCK_DATA: Set `true` to run wearables-bff with local fake/mock data instead of the database API. Default is `false`.
- BFF_DATABASE_API_URL: Value passed to wearables-bff `DATABASE_API_URL`. Must be a valid absolute URL even when `BFF_USE_MOCK_DATA=true` due to strict startup validation.
- BFF_DATABASE_API_TIMEOUT: Value passed to wearables-bff `DATABASE_API_TIMEOUT` (milliseconds). Must be a positive integer.
- PUBLIC_API_BASE_URL: Shared public API base URL used for both wearables-bff `BACKEND_URL` and web-frontend `runtimeConfig.apiBaseUrl`. Default is http://wearables.charite.de/api.
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

- INGRESS_HTTP_ONLY: Set true to deploy ingress routes without TLS/certificates/HTTPS redirect (test-only mode).
- INGRESS_HOST: Domain name for certificates.
- INGRESS_CERT_NAME: Certificate resource name.
- INGRESS_CERT_SECRET_NAME: Secret name where the certificate is stored.

### Grafana bootstrap auth (optional)
- GRAFANA_ADMIN_USER: Grafana admin username used by setup to configure datasource via API. Default is admin.
- GRAFANA_ADMIN_PASSWORD: Grafana admin password used by setup to configure datasource via API. Default is admin.
- GRAFANA_SUBPATH: Grafana URL subpath used for login/API calls during bootstrap. Default is /grafana.
