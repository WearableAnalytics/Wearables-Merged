# ClinicalAnalyticsPlatform

### Prerequisites for Local Deployment
- minikube >= v1.37.0
- kubectl: Client-Version >= v1.34.1, Kustomize Version: v5.7.1, Server Version: v1.34.0
- **Container Runtime**: e.g. Docker >= v27.3.1
- Influx CLI >= v2.7.5
- just >= 1.37.0

#### Recommended Tools for easy Monitoring
- k9s >= v0.50.15 (monitor the cluster)

### Start-up
Start **minikube**, make sure you allow **minikube** to access enough resources (especially when deploying **Apache Kafka**).
Due to **Apache Kafka's** heavy memory consumption, you should at least assign **7GB** of memory. 
To tune performance, you can also assign more compute resources by setting the `--cpus`-flag (e.g. `--cpus=4`).

```shell
minikube start --memory=8192
```

Next, please set a namespace within the cluster, which logically splits the cluster. Please don't forget to set the `-n`-flag to access/apply anything in the namespace.
Otherwise `kubectl` will not be able to find the requested pod/deployment/service.

```shell
kubectl create namespace <namespace>
```

#### Deploying the Services

To deploy **Kafka** execute following command in the root of the project
```shell
kubectl apply -f 'https://strimzi.io/install/latest?namespace=<namespace>'
kubectl apply -f ./k8s/kafka/kafka.yml -n <namespace>
```

---
To deploy **InfluxDB 2.7** execute following command in the root of the project:

```shell
kubectl apply -f ./k8s/influxdb/influx-pvc.yml -n <namespace>
kubectl apply -f ./k8s/influxdb/influx.yml -n <namespace>
```

Please forward the Influx-Port in a new Terminal-Tab, so you can access the shell of Influx on your local machine: 

```shell
kubectl port-forward svc/influx-service -n <namespace> 8086:8086
```

**Deprecated -> Only for Influx1:12**
To access the Influx-Shell please enter following command in another Terminal-Tab:
```shell
influx v1 shell
```

### Alternative: Just
For ease of use, you could also use the just commands to deploy everything:
This command starts a minikube cluster with `--cpus=4` and `--memory=7000`:
```shell
just start <namespace>
```

This command deploys a Strimzi-Kafka-Cluster, please use the same namespace as above:
```shell
just kafka <namespace>
```

This command deploys influx:2.7 (might migrate back to 1.12), please use the namespace as above:
```shell
just influx <namespace>
```
