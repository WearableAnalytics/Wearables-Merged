# ==========================================
# STAGE 1: Dependency Downloader
# ==========================================
FROM alpine:latest AS deps
RUN apk add --no-cache curl

# Download kubectl so the data scientist can submit SparkApplications directly
# from the Jupyter terminal.  Pin to a known-stable version that matches the
# cluster API; update together with the cluster upgrade.
RUN KUBECTL_VERSION="v1.31.0" && \
    curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" && \
    chmod +x kubectl
WORKDIR /jars

# Download all top-level AND transitive dependencies
# (Removed the duplicate AWS SDK 2.27.21 bundle to prevent classpath collisions)
RUN curl -O https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.13/4.1.1/spark-sql-kafka-0-10_2.13-4.1.1.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.7.0/kafka-clients-3.7.0.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.12.0/commons-pool2-2.12.0.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.13/4.1.1/spark-token-provider-kafka-0-10_2.13-4.1.1.jar \
    && curl -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.4.2/hadoop-aws-3.4.2.jar \
    && curl -O https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/2.29.52/bundle-2.29.52.jar \
    && curl -O https://repo1.maven.org/maven2/io/delta/delta-spark_2.13/4.1.0/delta-spark_2.13-4.1.0.jar \
    && curl -O https://repo1.maven.org/maven2/io/delta/delta-storage/4.1.0/delta-storage-4.1.0.jar

# ==========================================
# STAGE 2: Interactive Jupyter Environment
# ==========================================
# Use the official Jupyter PySpark image (already has Java, Python 3.11+, and Spark 4.1.1 configured)
FROM quay.io/jupyter/pyspark-notebook:spark-4.1.1

# Switch to root to copy files and install system packages
USER root

# 1. Copy the downloaded JARs into Jupyter's Spark jars directory
# NOTE: Jupyter installs Spark to /usr/local/spark, NOT /opt/spark
COPY --from=deps /jars/* /usr/local/spark/jars/

# Install kubectl for submitting SparkApplications from the Jupyter terminal
COPY --from=deps /kubectl /usr/local/bin/kubectl

# 2. Copy requirements file and install via pip
COPY spark_jobs/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install -r /tmp/requirements.txt

# 3. Setup workspace
# NOTE: Jupyter's default working directory is /home/jovyan/work
WORKDIR /home/jovyan/work

# Copy your specific subdirectories into the Jupyter workspace
COPY spark_jobs/jobs/ ./jobs/
COPY feast/feature_repo/ ./feature_repo/
# Training scripts and example SparkApplication manifest
COPY ml-dev/src/ ./src/

# 4. Fix permissions so the Jupyter user owns everything
# NOTE: Jupyter uses the `jovyan` user (UID 1000), NOT user 185
RUN chown -R ${NB_UID}:${NB_GID} /home/jovyan/work/

# Entrypoint wrapper: route Spark driver/executor commands to Spark's own
# entrypoint, and everything else (notebook, shell) to Jupyter's start.sh.
# The Spark operator expects /opt/entrypoint.sh to exist and handle the
# "driver" and "executor" sub-commands it passes as the container command.
#  ml-dev/spark-entrypoint.sh — a wrapper that routes:
#  - driver / executor / submit → Spark's real entrypoint at /usr/local/spark/kubernetes/dockerfiles/spark/entrypoint.sh
#  - Everything else → Jupyter's start.sh (notebook/shell use)
COPY ml-dev/spark-entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

# Switch back to the default Jupyter user so the notebook starts safely
USER ${NB_UID}

ENTRYPOINT ["/opt/entrypoint.sh"]
CMD []