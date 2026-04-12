# Kubernetes Resources

For this project we have the following resources (so far):

- Strimzi Kafka Operator
- Kafka Cluster (dual-role single-node)
- Kafka Connect Cluster
- InfluxDB
- Telegraf
- Mosquitto
- Mapper-Validator (custom / self-made)

## Namespaces

Resources are deployed via HELM. When a resource is created the `--namespace` flag can be used to specify the namespace a service is created in

All of our Helm charts are custom (except strimzi cluster operator) and are designed in a way that should allow us to spread resources across namespaces as we see best fit. Currently every service and its related resources have their own namespace.

## Vision

We should discuss an automated approach to the deployment (like GitOps, DevOps,  CI/CD) to automate this process and eliminate the margin for human error so that we have a stable cluster.

For the GitOps approach I also suggest prohibiting pushes to main and working with Pull Requests and Reviews to further eliminate the chance of error and struggles with bugs in infrastructure.

## Setup

All helm commands below assume you are running them from the gitops base directory.

### Apps

Before being able to deploy anything Kafka related, the strimzi operator needs to be deployed

`helm install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator --namespace kafka --create-namespace`

After that helm charts can be deployed. I suggest the `helm upgrade --install` instead of `helm install` since it is idempotent.

For debugging and checking that the generated yaml files are as expected the command can be appended with `--dry-run` which simulates the deployment without actually doing it.

The values that are set in the values.yaml files should work as is, if we stick to exactly the following commands, otherwise some values might need to be changed


**For deployment I suggest the following order to provide necessary dependecies:**

**Install Kakfa**

`helm upgrade --install kafka  ./apps/platform/kafka --values ./apps/platform/kafka/values.yaml --namespace kafka --create-namespace`

Then create necessary topics by opening an interactive shell in Kafka controller and running

`bin/kafka-topics.sh --create --topic <Name> --bootstrap-server localhost:9092 --partitions 1`

**ATTENTION**: When kafka is deleted via `helm uninstall kafka --namespace kafka` we need to delete the pvc for kafka manually, otherwise it will throw an error when redeployed

Currently, the image for this application is hosted on a public dockerhub repo on my personal account -> we need to find a more permanent solution for this too

Currently the mapper is running multithreaded as validation can take a long time. For that Kafka uses partitions. Each mapper instance is currently running 3 threads (See `.Values.envs.numStreamThreads`). To achieve that the following must be true:

`topic_partitions >= mapper_instances * num_stream_threads`

Where `topic_partitions` is the number of partitions of the raw data topic. 
This is necessary as each mapper instance handles parallelism by reading from multiple partitions. Partitioning logic (rekeying and rebalancing) is handled inside the mapper.

`helm upgrade --install mapper-validator  ./apps/services/mapper-validator --values ./apps/services/mapper-validator/values.yaml --namespace kafka --create-namespace`

**Install Influx**

`helm upgrade --install influxdb  ./apps/monitoring/influxdb --values ./apps/monitoring/influxdb/values.yaml --namespace influx --create-namespace`

**ATTENTION**: As of now telegraf always requires some manual configuration:
- after deploying Influx port forward and call `localhost:8086`
- there run setup create user, org, bucket, password
- copy the token that is generated and paste it into the command below


**Install telegraf** 

Here we also provide arguments to configure it to access influx.

```yaml
helm upgrade --install telegraf  ./apps/monitoring/telegraf --values ./apps/monitoring/telegraf/values.yaml --namespace telegraf \
--create-namespace \
--set config.influxProducer.org=<ORG> \
--set config.influxProducer.bucket=<BUCKET> \
--set config.influxProducer.token=<TOKEN> 
```

**Install the ingestion service**

Setup the import service

`helm upgrade --install importservice  ./apps/services/importservice --values ./apps/services/importservice/values.yaml --namespace importservice --create-namespace`

This will also configure IngressRoutes and needed middleware to resolve paths properly.

**Install grafana**

`helm upgrade --install grafana ./apps/monitoring/grafana --values ./apps/monitoring/grafana/values.yaml --namespace grafana --create-namespace`

This will also configure IngressRoutes and needed middleware to resolve paths properly.

**Install prod-postgres**

`helm upgrade --install prod-postgres ./apps/platform/prod-postgres --values ./apps/platform/prod-postgres/values.yaml --namespace prod-postgres --create-namespace`

**Install db-lord**

1. Set the needed secret values

```yaml
POSTGRES_SERVER: "postgres.postgres.svc.cluster.local"
POSTGRES_PORT: "5432"
POSTGRES_DB: "db"
POSTGRES_USER: "admin"
POSTGRES_PASSWORD: "password"

INFLUX_URL: "http://influxdb.influx.svc.cluster.local:8080"
INFLUX_ORG: "org"
INFLUX_BUCKET: "test"
INFLUX_TOKEN: "token"
```

2. Render and apply secrets

`helm template db-lord ./apps/services/db-lord --namespace db-lord -s templates/db-lord-secrets.yaml > db-lord-secrets.yaml`

`kubectl apply -f db-lord-secrets.yaml -n db-lord`

3. Render and apply the migration job

`helm template db-lord ./apps/services/db-lord --namespace db-lord -s templates/job-migrate.yaml > job-migrate.yaml`

`kubectl delete job db-lord-migrate -n db-lord --ignore-not-found`

`kubectl apply -f job-migrate.yaml -n db-lord`

4. Deploy db-lord

`helm upgrade --install db-lord ./apps/services/db-lord --namespace db-lord`


**Install extraction service**

1. Render and install the secret. Ensure that db-lord base url is set correctly.

`helm template extraction-service ./apps/services/extraction-service --namespace extraction-service -s templates/extraction-service-secrets.yaml > extraction-service-secrets.yaml`

`kubectl apply -f extraction-service-secrets.yaml -n extraction-service`

2. Install the extraction service

`helm upgrade --install extraction-service ./apps/services/extraction-service --namespace extraction-service --create-namespace`

**Install frontend applications**

1. Bootstrap the needed secrets

For that the following secrets need to be set:

```
RESEARCHER_API_ACCESS_TOKEN="<researcher-token>"
BREVO_API_KEY="<brevo-api-key>"
GRAFANA_JWT_PRIVATE_KEY_PATH="./secrets/grafana-jwt-private.pem"
```

`../scripts/bootstrap-runtime-secrets.sh`

2. Deploy the backend for the frontend (wearables-bff)

`helm upgrade --install wearables-bff ./apps/services/wearables-bff -n wearables-bff --create-namespace -f ./apps/services/wearables-bff/values.yaml`

3. Deploy the grafana proxy

`helm upgrade --install grafana-proxy ./apps/monitoring/grafana-proxy -n monitoring --create-namespace --set secret.name=grafana-auth-secrets -f ./apps/monitoring/grafana-proxy/values.yaml`

4. Deploy the web-frontend

`helm upgrade --install web ./apps/web-frontend -n web --create-namespace -f ./apps/web-frontend/values.yaml`


### Network

The deNBI cloud uses OpenStack and kubermatic. We have been assigned a public IP adress at `194.94.4.68`.

We have also been given a (possibly non-permanent solution) domain by Elias. The DNS entry for https://wearable-analytics.de points to our IP.

For security reasons the cluster nodes are running in a different network than the load balancer / ingress controller (traefik). You can take a look at the OpenStack dashboard under Network > Network Topology to get a better understanding.

The network is built up as follows:

Ingress Controller traefik (as k8s LB) deployed in ns `ingress`. General use traefik middleware and certificate for that namespace are also deployed in `ingress`. 

All services that should be externally exposed have their own https and http routes that are defined in their respective folders. Each namespace also needs an own cert for TLS since they and the secrets they rely on / manage are namespace scoped in k8s.

**Install the ingress controller**

The ingress controller is the publicly exposed service that forwards trafficto our services based ON `IngressRoute` resources. The latter are just route definitions and need a ingress controller to work.

`helm upgrade --install traefik  ./network/ingresscontroller --values ./network/ingresscontroller/values.yaml --namespace ingress --create-namespace`

This creates afew things (take a look into the folder). It is important that the network IDs provided are correct otherwise this will not work. (The LB runs in a different network than our worker nodes)

**Install the ingress**

This creates reusable ingress resources (like middleware etc.) and the ingress class they are based on (-> traefik).

`helm upgrade --install traefik-ingress  ./network/ingress --values ./network/ingress/values.yaml --namespace ingress --create-namespace`

## More

Run
```
kubectl exec -it kafka-dual-role-0  -n kafka  -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic {wearables-lp|wearables-fhir|wearables-lp} \
  --property print.value=true
```
 to watch the message travel through the system.