import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from mlflow.client import MlflowClient

# --- 0. CONFIGURATION ---
# Credentials come from the ml-dev-secrets / spark-pipeline-secrets Secret,
# which is kept in sync with Infisical (ml-pipeline project, prod environment).
# No credentials are hardcoded here.
MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI",
    "http://mlflow-tracking.ml-pipeline-mlflow.svc.cluster.local:5000",
)
MLFLOW_S3_ENDPOINT_URL = os.environ.get(
    "MLFLOW_S3_ENDPOINT_URL",
    "http://seaweedfs-s3.ml-pipeline-seaweedfs.svc.cluster.local:8333",
)
MODEL_NAME = "heart_rate_model"

# Connect MLflow to the remote tracking server and S3 artifact store.
# AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are already in the environment
# via envFrom (secretRef: ml-dev-secrets / spark-pipeline-secrets).
os.environ["MLFLOW_S3_ENDPOINT_URL"] = MLFLOW_S3_ENDPOINT_URL
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

# --- 1. SETUP DATA ---
data = pd.DataFrame({"value": np.random.uniform(0, 150, 1000)})
data["health_rate"] = (data["value"] // 10) * 10

X_train = data[["value"]]
y_train = data["health_rate"]

# --- 2. TRAIN ---
rf = RandomForestClassifier(n_estimators=50, max_depth=3)
rf.fit(X_train, y_train)

with mlflow.start_run() as run:
    signature = infer_signature(X_train, rf.predict(X_train))

    model_info = mlflow.sklearn.log_model(
        sk_model=rf,
        artifact_path="model",
        signature=signature,
        registered_model_name=MODEL_NAME,
    )

print(f"Model registered in MLflow registry as: {MODEL_NAME}")

client = MlflowClient()
model_version = model_info.registered_model_version

# Set alias "Production" — this is what KServe resolves via
# models:/heart_rate_model/Production.
# (transition_model_version_stage is deprecated in MLflow 3.x; aliases replace it)
client.set_registered_model_alias(
    name=MODEL_NAME,
    alias="Production",
    version=model_version,
)

print(f"Model version {model_version} aliased as 'Production'")
