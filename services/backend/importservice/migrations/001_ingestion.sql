-- Apply before starting the importer. Grant the runtime role DML, not schema ownership.
BEGIN;
CREATE SCHEMA IF NOT EXISTS ingestion;
CREATE TABLE ingestion.uploads (
    id uuid PRIMARY KEY,
    case_id text NOT NULL,
    participant_id text NOT NULL,
    request_key text NOT NULL,
    raw_sha256 text NOT NULL,
    raw_size integer NOT NULL,
    archive_key_id text NOT NULL,
    raw_ciphertext bytea NOT NULL,
    reading_count integer NOT NULL CHECK (reading_count > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (case_id, participant_id, request_key)
);
CREATE TABLE ingestion.records (
    id uuid PRIMARY KEY,
    first_upload_id uuid NOT NULL REFERENCES ingestion.uploads(id),
    record_key text NOT NULL UNIQUE,
    input_sha256 text NOT NULL,
    source_key text NOT NULL,
    identity_mode text NOT NULL CHECK (identity_mode IN ('source-record', 'upload-only')),
    archive_key_id text NOT NULL,
    payload_ciphertext bytea NOT NULL,
    generation integer NOT NULL DEFAULT 1 CHECK (generation > 0),
    outcome text NOT NULL DEFAULT 'pending' CHECK (outcome IN ('pending', 'normalized', 'rejected')),
    error_code text,
    mapper_version text,
    projection_key text UNIQUE,
    output_sha256 text,
    output_ciphertext bytea,
    timestamp_ns bigint,
    confirmed_at timestamptz,
    next_observation_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    result_conflict boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ingestion.upload_records (
    upload_id uuid NOT NULL REFERENCES ingestion.uploads(id),
    record_id uuid NOT NULL REFERENCES ingestion.records(id),
    PRIMARY KEY (upload_id, record_id)
);
CREATE TABLE ingestion.outbox (
    record_id uuid NOT NULL REFERENCES ingestion.records(id),
    generation integer NOT NULL,
    stage text NOT NULL CHECK (stage IN ('raw', 'projection')),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'leased', 'confirmed', 'blocked')),
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_id uuid,
    lease_until timestamptz,
    broker_partition integer,
    broker_offset bigint,
    error_code text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (record_id, generation, stage)
);
CREATE INDEX ingestion_outbox_due ON ingestion.outbox (available_at) WHERE state IN ('pending', 'leased');
CREATE INDEX ingestion_upload_scope ON ingestion.uploads (case_id, participant_id, created_at);
CREATE INDEX ingestion_records_unconfirmed ON ingestion.records (updated_at) WHERE outcome = 'normalized' AND confirmed_at IS NULL;
CREATE INDEX ingestion_outbox_confirmed ON ingestion.outbox (updated_at) WHERE state='confirmed';
CREATE INDEX ingestion_records_active ON ingestion.records (id) WHERE outcome='pending' OR (outcome='normalized' AND confirmed_at IS NULL);
CREATE TABLE ingestion.events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id uuid REFERENCES ingestion.records(id),
    upload_id uuid REFERENCES ingestion.uploads(id),
    generation integer,
    code text NOT NULL,
    mapper_version text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMIT;
