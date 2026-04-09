FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "feast[postgres]"

COPY feast/feature_repo/ /app/feature_repo/

WORKDIR /app/feature_repo

# Apply will be run via init container or setup job
CMD ["feast", "serve", "--host", "0.0.0.0", "--port", "6566"]
