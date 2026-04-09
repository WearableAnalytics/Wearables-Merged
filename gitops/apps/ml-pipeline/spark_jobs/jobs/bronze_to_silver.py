"""
Structured Streaming: Delta Bronze -> Delta Silver (via LakeFS)
Parses raw line-protocol payloads into structured columns.
"""
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, regexp_extract, split, struct, to_date,
)

# --- Config from environment ---
S3_ENDPOINT = os.environ["S3_ENDPOINT"]
S3_ACCESS_KEY = os.environ["S3_ACCESS_KEY"]
S3_SECRET_KEY = os.environ["S3_SECRET_KEY"]
BRONZE_BUCKET = os.environ.get("BRONZE_BUCKET", "lake-bronze")
BRONZE_PATH = f"s3a://{BRONZE_BUCKET}/bronze_datalake"

LAKEFS_ENDPOINT = os.environ["LAKEFS_ENDPOINT"]
LAKEFS_ACCESS_KEY = os.environ["LAKEFS_ACCESS_KEY"]
LAKEFS_SECRET_KEY = os.environ["LAKEFS_SECRET_KEY"]

SILVER_LAKEFS_REPO = os.environ.get("SILVER_LAKEFS_REPO", "lake-silver")
SILVER_LAKEFS_BRANCH = os.environ.get("SILVER_LAKEFS_BRANCH", "processed")
SILVER_PATH = f"s3a://{SILVER_LAKEFS_REPO}/{SILVER_LAKEFS_BRANCH}/silver_datalake"
SILVER_CHECKPOINT_PATH = f"s3a://{SILVER_LAKEFS_REPO}/{SILVER_LAKEFS_BRANCH}/_checkpoints/structured_streaming_bronze_to_silver"

# --- Spark Session ---
spark = SparkSession.builder \
    .appName("BRONZE_TO_SILVER_STREAM") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .config("spark.delta.logStore.class", "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore") \
    .getOrCreate()

# --- S3A config: per-bucket credentials (Bronze=SeaweedFS, Silver=LakeFS) ---
per_bucket_settings = {
    f"fs.s3a.bucket.{BRONZE_BUCKET}.endpoint": S3_ENDPOINT,
    f"fs.s3a.bucket.{BRONZE_BUCKET}.access.key": S3_ACCESS_KEY,
    f"fs.s3a.bucket.{BRONZE_BUCKET}.secret.key": S3_SECRET_KEY,
    f"fs.s3a.bucket.{SILVER_LAKEFS_REPO}.endpoint": LAKEFS_ENDPOINT,
    f"fs.s3a.bucket.{SILVER_LAKEFS_REPO}.access.key": LAKEFS_ACCESS_KEY,
    f"fs.s3a.bucket.{SILVER_LAKEFS_REPO}.secret.key": LAKEFS_SECRET_KEY,
}
global_settings = {
    "fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    "fs.s3a.path.style.access": "true",
    "fs.s3a.connection.ssl.enabled": "false",
    "fs.s3a.endpoint.region": "us-east-1",
}

hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
for k, v in {**global_settings, **per_bucket_settings}.items():
    spark.conf.set(f"spark.hadoop.{k}", v)
    hadoop_conf.set(k, v)

# --- Read Bronze, transform to Silver ---
bronze_stream = spark.readStream.format("delta").load(BRONZE_PATH)

silver_df = (
    bronze_stream
    .withColumn("header_part", regexp_extract(col("raw_payload"), r"^([^ ]+) ", 1))
    .withColumn("value", regexp_extract(col("raw_payload"), r"value=([\d\.]+)", 1).cast("double"))
    .withColumn("raw_ts", regexp_extract(col("raw_payload"), r" (\d+)$", 1).cast("long"))
    .withColumn("device_id", regexp_extract(col("header_part"), r"device-id=([^, ]+)", 1))
    .withColumn("measurement", split(col("header_part"), ",").getItem(0))
    .withColumn("tags", struct(
        regexp_extract(col("header_part"), r"category=([^, ]+)", 1).alias("category"),
        regexp_extract(col("header_part"), r"version=([^, ]+)", 1).alias("version"),
    ))
    .withColumn("event_time", (col("raw_ts") / 1_000_000_000).cast("timestamp"))
    .withColumn("event_date", to_date(col("event_time")))
    .select("device_id", "event_date", "measurement", "value",
            "event_time", "tags", "ingestion_timestamp")
)

# --- Write Silver Delta ---
query = (
    silver_df.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", SILVER_CHECKPOINT_PATH)
    .start(SILVER_PATH)
)

query.awaitTermination()
