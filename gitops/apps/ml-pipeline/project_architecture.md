# Project Structure

## Folder structure

```
.
├── build.sh                  # Build Docker images (mlflow, feast, spark, jupyter)
├── deploy.sh                 # Deploy all components to Kubernetes
├── deploy-infisical.sh       # Deploy Infisical secret management server + operator
├── teardown.sh               # Tear down all deployed resources
├── docs/
│   ├── data-flow.md          # Detailed pipeline architecture and env var reference
│   ├── components-map.md     # Component-to-namespace mapping and DNS endpoints
│   └── deployment.md         # Deployment quick start
├── spark_jobs/               # 3× Spark Structured Streaming jobs (SparkApplication CRDs)
│   ├── jobs/raw_to_bronze.py
│   ├── jobs/bronze_to_silver.py
│   ├── jobs/silver_to_prediction.py
│   └── Dockerfile            # Base: apache/spark:4.1.1-python3
├── ml-dev/                   # Jupyter dev notebook + MLflow training job
│   ├── src/ml_flow_training.py
│   └── Dockerfile            # Base: quay.io/jupyter/pyspark-notebook:spark-4.1.1
├── mlflow/                   # MLflow Tracking Server (Deployment + Service)
├── feast/                    # Feast Feature Server + feature definitions
├── kserve/                   # KServe InferenceService + ClusterStorageContainer
├── seaweedfs/                # SeaweedFS Helm chart (S3-compatible object storage)
├── lakefs/                   # LakeFS Helm chart (data versioning on SeaweedFS)
├── argo/                     # Argo Workflows operator (Kustomize)
├── spark-operator/           # Spark Operator Helm values
├── infisical/                # Infisical Helm chart + InfisicalSecret CRDs per component
├── SCRIPTS/
│   ├── postgres_setup/       # PostgreSQL provisioning via Argo Workflow
│   ├── seaweedfs_setup/      # SeaweedFS bucket + S3 secret provisioning
│   ├── lakefs_setup/         # LakeFS repo + branch creation
│   └── lakefs_workflows/     # LakeFS commit/merge cron jobs
└── debug/                    # Debug utilities (node-cleaner DaemonSet, spark-debug)
```

## Kubernetes Namespaces

| Namespace | Component |
|-----------|-----------|
| `ml-pipeline-spark-jobs` | Raw-to-Bronze, Bronze-to-Silver, Silver-to-Prediction streaming jobs |
| `ml-pipeline-ml-dev` | Jupyter notebook (`:8888`) + MLflow training SparkApplication |
| `ml-pipeline-mlflow` | MLflow Tracking Server (`:5000`) |
| `ml-pipeline-feast` | Feast Feature Server (`:6566`) |
| `ml-pipeline-kserve-models` | KServe InferenceService |
| `ml-pipeline-seaweedfs` | SeaweedFS S3 gateway (`:8333`) |
| `ml-pipeline-lakefs` | LakeFS data versioning (`:80`) |
| `ml-pipeline-argo` | Argo Workflows operator + setup workflows |
| `ml-pipeline-spark-operator` | Spark Operator |
| `prod-postgres` | Shared PostgreSQL metadata store (`:5432`) |
| `infisical` | Infisical secret management server |
| `ml-pipeline-debug` | Debug utilities |


## Secret Management

All secrets are managed via Infisical. The `InfisicalSecret` operator syncs secrets every 60 seconds from project `ml-pipeline` / env `prod` into Kubernetes Secrets:

| Kubernetes Secret | Namespace |
|-------------------|-----------|
| `mlflow-secrets` | `ml-pipeline-mlflow` |
| `feast-secrets` | `ml-pipeline-feast` |
| `spark-pipeline-secrets` | `ml-pipeline-spark-jobs` |
| `lakefs-secrets` | `ml-pipeline-lakefs` |
| `seaweedfs-s3-secret` | `ml-pipeline-seaweedfs` |
| `ml-dev-secrets` | `ml-pipeline-ml-dev` |
| `kserve-secrets` | `ml-pipeline-kserve-models` |
| `postgres-setup-secrets` | `prod-postgres` |

## Internal DNS Endpoints

| Endpoint | Port | Used by |
|----------|------|---------|
| `mlflow-tracking.ml-pipeline-mlflow.svc.cluster.local` | 5000 | Spark training job, Jupyter, KServe |
| `seaweedfs-s3.ml-pipeline-seaweedfs.svc.cluster.local` | 8333 | LakeFS, MLflow artifacts, KServe model download |
| `lakefs.ml-pipeline-lakefs.svc.cluster.local` | 80 | Setup workflows, LakeFS cron jobs |
| `prod-postgres.prod-postgres.svc.cluster.local` | 5432 | SeaweedFS metadata, MLflow backend, Feast registry |
| `infisical-infisical-standalone-infisical.infisical.svc.cluster.local` | 8080 | All `InfisicalSecret` CRDs |