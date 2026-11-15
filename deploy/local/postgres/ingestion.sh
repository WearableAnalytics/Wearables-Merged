#!/bin/sh
set -eu
# Local-only bootstrap. This job receives database credentials, never archive keys.
psql -v ON_ERROR_STOP=1 \
  -v runtime_password="$INGEST_RUNTIME_PASSWORD" \
  -v migration_password="$INGEST_MIGRATION_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE wearables_ingest LOGIN PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='wearables_ingest') \gexec
SELECT format('CREATE ROLE wearables_migrate LOGIN PASSWORD %L', :'migration_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='wearables_migrate') \gexec
SELECT 'CREATE DATABASE wearables_ingestion OWNER wearables_migrate'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='wearables_ingestion') \gexec
SQL
