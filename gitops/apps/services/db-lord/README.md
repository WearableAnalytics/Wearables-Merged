# Database Management Service - Helm Chart Documentation

This Helm chart deploys a **Database Management Service** that requires credentials and connection details for:
- PostgreSQL
- InfluxDB

Sensitive configuration is provided to the application via a Kubernetes `Secret` referenced by name through Helm values.

---
### Prerequisites
- Kubernetes 1.24+
- Helm 3.x
- A pre-configured PostgreSQL instance
- A pre-configured InfluxDB instance

---
### Installation

#### 1. Create Namespace (if not exisiting)
```shell
kubectl create namespace <namespace-name>
```

#### 2. Create the Kubernetes Secret
>[!IMPORTANT]   
> This chart does not create database secrets automatically.
> You must create the Secret **before** installing the chart.

Example-Values for the Kubernetes-Secret parameters:

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

Please be aware that you must be careful how you deploy the secrets (use `kubectl`)!

But for testing, you can also do following or just set the values in the `values.yaml` file.

You can also leave the `POSTGRES_PASSWORD` and `INFLUX_TOKEN` out and set them via CLI like following:
```shell
helm install <name> ./<path> \
  --set env.POSTGRES_PASSWORD="password"
  --set env.INFLUX_TOKEN="token"
```
> [!WARNING]
> Secrets passed via `--set` can appear in shell history or logs. Avoid in production!


Apply it:
```shell
kubectl apply -n <namespace-name> -f ./path/to/secret.yaml
```

Ensure the secret was created successfully:
```shell
kubectl get secret db-lord-secrets -n <namespace-name>
```

### Container Image

The Database Management Service container image is configurable via Helm values.

> [!WARNING]  
> The image is currently in **beta**. Breaking changes may be introduced at any time and backward compatibility is not guaranteed.

**Beta Config:**
```yaml
image:
  repository: stahlco/db_lord
  pullPolicy: Always
  tag: "beta"
```
Once the first stable release of the Database Management Servivce is completed the default image tag will be switched to:
To deploy the most recent version of the image, update the `image.tag` value to `latest`.
```yaml
tag: "latest"
```
At that point, `latest` will represent a stable release. Versioned tags will also be introduced for reproducible deployments.
