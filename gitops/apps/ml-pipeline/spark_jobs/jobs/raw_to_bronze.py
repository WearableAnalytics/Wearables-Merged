"""
Structured Streaming: Kafka -> Delta Bronze Layer (SeaweedFS S3)
Reads raw wearables data from Kafka and lands it as a Delta table.
"""
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, to_date

# --- Config from environment ---
S3_ENDPOINT = os.environ["S3_ENDPOINT"]
S3_ACCESS_KEY = os.environ["S3_ACCESS_KEY"]
S3_SECRET_KEY = os.environ["S3_SECRET_KEY"]
BUCKET_NAME = os.environ.get("BRONZE_BUCKET", "lake-bronze")

BRONZE_PATH = f"s3a://{BUCKET_NAME}/bronze_datalake"
# CHECKPOINT_PATH = f"s3a://{BUCKET_NAME}/_checkpoints/structured_streaming_kafka_lp_to_bronze" #unfortuately, SeaweedFS S3 doesn't support the atomic rename operation required for Spark's checkpointing, so we have to use a local filesystem path for checkpoints.
CHECKPOINT_PATH = "file:///tmp/streaming_checkpoints/kafka_lp_to_bronze"

KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka-kafka-bootstrap.kafka.svc.cluster.local:9092",
)
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "wearables-lp")

# --- Spark Session ---
spark = SparkSession.builder \
    .appName("RAW_TO_BRONZE_STREAM") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .config("spark.delta.logStore.class", "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore") \
    .config("spark.jars.ivy", "/tmp/.ivy2") \
    .getOrCreate()


# --- S3A / Hadoop config ---
s3a_settings = {
    "fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    "fs.s3a.endpoint": S3_ENDPOINT,
    "fs.s3a.access.key": S3_ACCESS_KEY,
    "fs.s3a.secret.key": S3_SECRET_KEY,
    "fs.s3a.path.style.access": "true",
    "fs.s3a.connection.ssl.enabled": "false",
    "fs.s3a.endpoint.region": "us-east-1",
}

hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
for k, v in s3a_settings.items():
    spark.conf.set(f"spark.hadoop.{k}", v)
    hadoop_conf.set(k, v)

# --- Read from Kafka ---
raw_stream = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", KAFKA_TOPIC)
    .option("startingOffsets", "earliest")
    .load()
)

bronze_df = raw_stream.select(
    col("key").cast("binary"),
    col("value").cast("string").alias("raw_payload"),
    col("topic"),
    col("partition"),
    col("offset"),
    col("timestamp").alias("kafka_timestamp"),
    current_timestamp().alias("ingestion_timestamp"),
    to_date(current_timestamp()).alias("ingestion_date"),
)

# --- Write to Delta ---
query = (
    bronze_df.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", CHECKPOINT_PATH)
    .option("path", BRONZE_PATH)
    .option("mergeSchema", "true")
    .start()
)

query.awaitTermination()
