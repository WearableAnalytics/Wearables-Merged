# Data Analytics Layer (aka. ML Pipeline) 

## Deployment

### Prerequisites

#### Tools
- Kubernetes cluster with `kubectl` configured
- Helm 3
- Docker (for building images)

#### Input and output destinations
The following should be deployed first from the main platrofm:
- Kafka cluster reachable from within the cluster
- InfluxDB reachable from within the cluster

### 1. Build Docker Images

```bash
./build.sh
```

Builds and pushes images to the `wearables42` registry:
- `wearables42/streaming-ml-pipeline:latest` (Spark jobs)
- `wearables42/mlflow-server:latest`
- `wearables42/feast-server:latest`
- `wearables42/spark-notebook:latest` (Jupyter)

### 2. Deploy Infisical (Secret Management)

```bash
./deploy-infisical.sh
```

Then populate secrets via the Infisical UI or CLI into project `ml-pipeline` / env `prod`. See script `infisical/secrets/bootstrap.sh` for handy automation of secret bootstraping.

### 3. Deploy main components

```bash
./deploy.sh
```

Deploys in order: Argo Workflows → SeaweedFS → LakeFS → PostgreSQL → MLflow → Feast → Spark Operator → Spark Jobs → KServe → Spark Notebook.

```bash
./deploy.sh --help          # Show options
./deploy.sh --dry-run       # Print what would be applied
./deploy.sh --from-step N   # Resume from a specific step
```

### Teardown

```bash
./teardown.sh
```

## Further Reading
- [`project_architecture.md`](project_architecture.md) — Folder structure, Kubernetes namespaces, secret management, and detailed architecture overview
