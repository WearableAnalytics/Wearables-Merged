FROM ghcr.io/mlflow/mlflow:v3.10.1

# The official MLflow image does not ship with a PostgreSQL driver.
# psycopg2-binary is required for --backend-store-uri=postgresql://...
RUN pip install --no-cache-dir psycopg2-binary