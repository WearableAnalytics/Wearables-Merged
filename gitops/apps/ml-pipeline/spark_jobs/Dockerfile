FROM alpine:latest AS deps
RUN apk add --no-cache curl
WORKDIR /jars

# Download all top-level AND transitive dependencies
RUN curl -O https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.13/4.1.1/spark-sql-kafka-0-10_2.13-4.1.1.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.7.0/kafka-clients-3.7.0.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.12.0/commons-pool2-2.12.0.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.13/4.1.1/spark-token-provider-kafka-0-10_2.13-4.1.1.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.4.2/hadoop-aws-3.4.2.jar \
    && curl -O https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.29.52/bundle-2.29.52.jar \
    && curl -O https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.27.21/bundle-2.27.21.jar \
    && curl -O https://repo1.maven.org/maven2/io/delta/delta-spark_2.13/4.1.0/delta-spark_2.13-4.1.0.jar \
    && curl -O https://repo1.maven.org/maven2/io/delta/delta-storage/4.1.0/delta-storage-4.1.0.jar

FROM apache/spark:4.1.1-python3
USER root

# Spark 4.1.1 ships with Python 3.11+ — just install pip and dev headers
RUN apt-get update && \
    apt-get install -y python3-pip python3-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Force PySpark to use the image's python3
ENV PYSPARK_PYTHON=/usr/bin/python3
ENV PYSPARK_DRIVER_PYTHON=/usr/bin/python3
# ----

# Copy all JARs from the downloader stage into Spark's native classpath
COPY --from=deps /jars/* /opt/spark/jars/

# 1. Copy requirements file separately to leverage layer caching
COPY spark_jobs/requirements.txt /tmp/requirements.txt

# 2. Install using the cache mount WITHOUT --no-cache-dir, and strictly using python3
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install -r /tmp/requirements.txt

# Use WORKDIR to simplify paths
WORKDIR /opt/spark/work-dir

# Copy contents into specific subdirectories
COPY spark_jobs/jobs/ ./jobs/
COPY feast/feature_repo/ ./feature_repo/
RUN find /opt/spark/work-dir -maxdepth 2
RUN chown -R 185:185 /opt/spark/work-dir/
USER 185
