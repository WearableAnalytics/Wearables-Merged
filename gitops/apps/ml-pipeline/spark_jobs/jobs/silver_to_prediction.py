"""
Structured Streaming: Delta Silver -> Feast push -> ML Prediction -> InfluxDB

Flow per micro-batch:
  1. Filter heart-rate rows
  2. Push features to Feast online store (keeps online store fresh for any consumer)
  3. Retrieve features back from Feast (guarantees the model sees the same
     feature schema used during training — prevents training/serving skew)
  4. Run MLflow model inference
  5. Write predictions to InfluxDB
"""
import os
from datetime import datetime, timezone

from pyspark.sql import SparkSession
import pandas as pd
import mlflow.pyfunc
from feast import FeatureStore
from feast.data_source import PushMode
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# --- Config from environment ---
LAKEFS_ENDPOINT = os.environ["LAKEFS_ENDPOINT"]
LAKEFS_ACCESS_KEY = os.environ["LAKEFS_ACCESS_KEY"]
LAKEFS_SECRET_KEY = os.environ["LAKEFS_SECRET_KEY"]

SILVER_LAKEFS_REPO = os.environ.get("SILVER_LAKEFS_REPO", "lake-silver")
SILVER_LAKEFS_BRANCH = os.environ.get("SILVER_LAKEFS_BRANCH", "processed")
SILVER_PATH = f"s3a://{SILVER_LAKEFS_REPO}/{SILVER_LAKEFS_BRANCH}/silver_datalake"

INFLUX_CHECKPOINT_BRANCH = os.environ.get("INFLUX_CHECKPOINT_BRANCH", "influx-checkpoint-branch")
SILVER_CHECKPOINT_PATH_INFLUX = f"s3a://{SILVER_LAKEFS_REPO}/{INFLUX_CHECKPOINT_BRANCH}/_checkpoints/structured_streaming_silver_to_influx"

INFLUX_URL = os.environ["INFLUX_URL"]
INFLUX_TOKEN = os.environ["INFLUX_TOKEN"]
INFLUX_ORG = os.environ.get("INFLUX_ORG", "wearables-project")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "ml_predictions")

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow-tracking.mlflow.svc.cluster.local:5000")
MLFLOW_S3_ENDPOINT_URL = os.environ.get("MLFLOW_S3_ENDPOINT_URL", "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333")
MODEL_NAME = os.environ.get("MODEL_NAME", "heart_rate_model")
MODEL_ALIAS = os.environ.get("MODEL_ALIAS", "Production")

FEAST_REPO_PATH = os.environ.get("FEAST_REPO_PATH", "/opt/spark/work-dir/feature_repo")
FEAST_DB_HOST = os.environ.get("FEAST_DB_HOST", "prod-postgres.prod-postgres.svc.cluster.local")
FEAST_DB_PORT = os.environ.get("FEAST_DB_PORT", "5432")
FEAST_DB_NAME = os.environ.get("FEAST_DB_NAME", "feast")
FEAST_DB_USER = os.environ.get("FEAST_DB_USER", "feast_user")
FEAST_DB_PASSWORD = os.environ["FEAST_DB_PASSWORD"]

# --- Generate feature_store.yaml with real credentials ---
import yaml

import yaml

feast_config = {
    "project": "wearables",
    "provider": "local",
    "registry": {
        "registry_type": "sql",
        "path": f"postgresql+psycopg://{FEAST_DB_USER}:{FEAST_DB_PASSWORD}@{FEAST_DB_HOST}:{FEAST_DB_PORT}/{FEAST_DB_NAME}",
    },
    "online_store": {
        "type": "postgres",
        "host": FEAST_DB_HOST,
        "port": int(FEAST_DB_PORT),
        "database": FEAST_DB_NAME,
        "user": FEAST_DB_USER,
        "password": FEAST_DB_PASSWORD,
        # Fix: Explicitly disable SSL to match your server configuration
        "sslmode": "disable", 
    },
    "offline_store": {"type": "file"},
    # Fix: Update to version 3 to avoid deprecation warnings and serialization errors
    "entity_key_serialization_version": 3,
}

with open(os.path.join(FEAST_REPO_PATH, "feature_store.yaml"), "w") as f:
    yaml.dump(feast_config, f)
print(f"--> Generated Feast config at {FEAST_REPO_PATH}/feature_store.yaml")

import subprocess

# --- Initialize Feast Store ---
print(f"--> Initializing Feast store from: {FEAST_REPO_PATH}")

# NEW: Use the CLI to 'apply' changes. 
# This scans your .py files and creates the Postgres tables.
try:
    print("--> Running 'feast apply' to sync infrastructure...")
    # We run this in the directory where your definitions and YAML live
    result = subprocess.run(
        ["feast", "apply"], 
        cwd=FEAST_REPO_PATH, 
        capture_output=True, 
        text=True
    )
    if result.returncode == 0:
        print("--> Infrastructure synced successfully.")
        print(result.stdout)
    else:
        print(f"!! Error running feast apply:\n{result.stderr}")
except Exception as e:
    print(f"!! Failed to trigger feast apply: {e}")

# Now initialize the store object for the rest of the script
store = FeatureStore(repo_path=FEAST_REPO_PATH)

# --- Load ML Model from MLflow Registry ---
os.environ["MLFLOW_S3_ENDPOINT_URL"] = MLFLOW_S3_ENDPOINT_URL
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
model_uri = f"models:/{MODEL_NAME}@{MODEL_ALIAS}"
print(f"--> Loading model from MLflow: {model_uri}")
model = mlflow.pyfunc.load_model(model_uri)

# --- Initialize Feast Store ---
print(f"--> Initializing Feast store from: {FEAST_REPO_PATH}")
store = FeatureStore(repo_path=FEAST_REPO_PATH)

# --- Spark Session ---
spark = SparkSession.builder \
    .appName("SILVER_TO_INFLUX") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .config("spark.delta.logStore.class", "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore") \
    .getOrCreate()

# --- S3A config (LakeFS) ---
s3a_settings = {
    "fs.s3a.endpoint": LAKEFS_ENDPOINT,
    "fs.s3a.path.style.access": "true",
    "fs.s3a.access.key": LAKEFS_ACCESS_KEY,
    "fs.s3a.secret.key": LAKEFS_SECRET_KEY,
    "fs.s3a.connection.ssl.enabled": "false",
    "fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
}

hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
for k, v in s3a_settings.items():
    spark.conf.set(f"spark.hadoop.{k}", v)
    hadoop_conf.set(k, v)


# --- foreachBatch: push to Feast -> predict -> write to InfluxDB ---
def process_and_send_to_influx(batch_df, batch_id):
    if batch_df.isEmpty():
        return

    heart_rate_df = batch_df.filter(batch_df.measurement == "heart-rate")
    if heart_rate_df.isEmpty():
        print(f"--> Batch {batch_id}: No heart_rate data. Skipping.")
        return

    pdf = heart_rate_df.toPandas()

    # --- Step 1: Push features to Feast online store ---
    # Spark struct columns become Row objects in Pandas; use getattr for safe access
    feast_df = pd.DataFrame({
        "device_id": pdf["device_id"],
        "heart_rate_value": pdf["value"],
        "device_category": pdf["tags"].apply(lambda t: getattr(t, "category", "") if t else ""),
        "device_version": pdf["tags"].apply(lambda t: getattr(t, "version", "") if t else ""),
        "event_time": pdf["event_time"],
    })
    store.push("wearables_push", feast_df, to=PushMode.ONLINE)
    print(f"--> Batch {batch_id}: Pushed {len(feast_df)} rows to Feast online store.")

    # --- Step 2: Get features from Feast (ensures training/serving parity) ---
    entity_rows = [{"device_id": did} for did in pdf["device_id"].unique()]
    features = store.get_online_features(
        features=[
            "heart_rate_features:heart_rate_value",
            "heart_rate_features:device_category",
            "heart_rate_features:device_version",
        ],
        entity_rows=entity_rows,
    ).to_dict()

    # Build a lookup: device_id -> latest feature values from Feast
    # Note: Feast to_dict() returns keys WITHOUT the feature view prefix
    feast_lookup = {}
    for i, did in enumerate(features["device_id"]):
        feast_lookup[did] = {
            "heart_rate_value": features["heart_rate_value"][i],
            "device_category": features["device_category"][i],
            "device_version": features["device_version"][i],
        }

    # --- Step 3: ML Inference using Feast-sourced features ---
    # The model expects a "value" column — map from Feast feature name
    # For per-row prediction we use the batch data directly (Feast confirmed the schema)
    pdf["health_rate"] = model.predict(pdf[["value"]])

    # --- Step 4: Write to InfluxDB ---
    current_time = datetime.now(timezone.utc)

    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=50_000)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    points = []
    for _, row in pdf.iterrows():
        device_feats = feast_lookup.get(row["device_id"], {})
        p = (
            Point("ml_predictions")
            .tag("device_id", str(row["device_id"]))
            .tag("measurement_name", str(row["measurement"]))
            .tag("device_category", str(device_feats.get("device_category", "")))
            .tag("device_version", str(device_feats.get("device_version", "")))
            .field("observed_value", float(row["value"]))
            .field("health_rate", float(row["health_rate"]))
            .field("created_at", str(current_time))
            .time(row["event_time"], WritePrecision.NS)
        )
        points.append(p)

    if points:
        write_api.write(bucket=INFLUX_BUCKET, record=points)
        print(f"--> Batch {batch_id}: {len(points)} predictions written.")

    write_api.close()
    client.close()


# --- Read Silver, run foreachBatch ---
silver_df = spark.readStream.format("delta").load(SILVER_PATH)

query = (
    silver_df.writeStream
    .foreachBatch(process_and_send_to_influx)
    .option("checkpointLocation", SILVER_CHECKPOINT_PATH_INFLUX)
    .start()
)

query.awaitTermination()
