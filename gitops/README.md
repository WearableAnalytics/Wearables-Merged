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

### Apps

Before being able to deploy anything Kafka related, the strimzi operator needs to be deployed

`helm install strimzi-cluster-operator oci://quay.io/strimzi-helm/strimzi-kafka-operator --namespace kafka --create-namespace`

After that helm charts can be deployed. I suggest the `helm upgrade --install` instead of `helm install` since it is idempotent.

For debugging and checking that the generated yaml files are as expected the command can be appended with `--dry-run` which simulates the deployment without actually doing it.

The values that are set in the values.yaml files should work as is, if we stick to exactly the following commands, otherwise some values might need to be changed


**For deployment I suggest the following order to provide necessary dependecies:**

**Install Kakfa**

`helm upgrade --install kafka  ./kafka --values ./kafka/values.yaml --namespace kafka --create-namespace`

Then create necessary topics by opening an interactive shell in Kafka controller and running

`bin/kafka-topics.sh --create --topic <Name> --bootstrap-server localhost:9092 --partitions 1`

**ATTENTION**: When kafka is deleted via `helm uninstall kafka --namespace kafka` we need to delete the pvc for kafka manually, otherwise it will throw an error when redeployed

Currently, the image for this application is hosted on a public dockerhub repo on my personal account -> we need to find a more permanent solution for this too

`helm upgrade --install mapper-validator  ./mapper-validator --values ./mapper-validator/values.yaml --namespace kafka --create-namespace`

**Install Influx**

`helm upgrade --install influxdb  ./influxdb --values ./influxdb/values.yaml --namespace influx --create-namespace`

**ATTENTION**: As of now telegraf always requires some manual configuration:
- after deploying Influx port forward and call `localhost:8086`
- there run setup create user, org, bucket, password
- copy the token that is generated and paste it into the command below


**Install telegraf** 

Here we also provide arguments to configure it to access influx.

```yaml
helm upgrade --install telegraf  ./telegraf --values ./telegraf/values.yaml --namespace telegraf \
--create-namespace \
--set config.influxProducer.org=<ORG> \
--set config.influxProducer.bucket=<BUCKET> \
--set config.influxProducer.token=<TOKEN> 
```

**Install the ingestion service**

Setup the import service

`helm upgrade --install importservice  ./importservice --values ./importservice/values.yaml --namespace importservice --create-namespace`

### Network

The deNBI cloud uses OpenStack and kubermatic. We have been assigned a public IP adress at `194.94.4.68`.

For security reasons the cluster nodes are running in a different network than the load balancer / ingress controller (traefik). You can take a look at the OpenStack dashboard under Network > Network Topology to get a better understanding.

**Install the ingress controller**

The ingress controller is the publicly exposed service that forwards trafficto our services based ON `Ingress` resources. The latter are just route definitions and need a ingress controller to work.

`helm upgrade --install traefik  ./ingresscontroller --values ./ingresscontroller/values.yaml --namespace ingress --create-namespace`

This creates afew things (take a look into the folder). It is important that the network IDs provided are correct otherwise this will not work.

**Install the ingress**

This creates an ingress (route) and the ingress class it is based on. (in our case traefik)

`helm upgrade --install traefik  ./ingresscontroller --values ./ingresscontroller/values.yaml --namespace ingress --create-namespace`

**ATTENTION**: This needs to run in the same namespace as the import service, otherwise the Ingress route does not work

## More

Run
```
kubectl exec -it kafka-dual-role-0  -n kafka  -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic {wearables-lp|wearables-fhir|wearables-lp} \
  --property print.value=true
```
 to watch the message travel through the system.