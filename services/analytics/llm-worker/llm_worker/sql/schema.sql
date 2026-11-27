-- Semantic task worker: one queue for every kind of task (pipeline events and chat questions).
CREATE SCHEMA IF NOT EXISTS tasks;

CREATE TABLE IF NOT EXISTS tasks.task_runs (
    task_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template       text NOT NULL,
    params         jsonb NOT NULL DEFAULT '{}',
    prompt         text NOT NULL,
    trigger        text NOT NULL CHECK (trigger IN ('pipeline', 'chat')),
    submitted_by   text NOT NULL,
    priority       integer NOT NULL DEFAULT 10,  -- lower runs first
    dedup_key      text UNIQUE,

    state          text NOT NULL DEFAULT 'pending'
                   CHECK (state IN ('pending', 'processing', 'finished', 'failed')),
    attempts       integer NOT NULL DEFAULT 0,
    run_after      timestamptz NOT NULL DEFAULT now(),
    locked_by      text,
    locked_until   timestamptz,

    answer         text,
    result         jsonb,
    error          text,
    model          text,
    spec_versions  jsonb,

    created_at     timestamptz NOT NULL DEFAULT now(),
    started_at     timestamptz,
    finished_at    timestamptz
);

CREATE INDEX IF NOT EXISTS task_runs_open
    ON tasks.task_runs (priority, run_after, task_id)
    WHERE state IN ('pending', 'processing');

-- Only alert_triage tasks from the pipeline write here (enforced by the worker).
CREATE TABLE IF NOT EXISTS tasks.notifications (
    notification_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id         bigint NOT NULL UNIQUE REFERENCES tasks.task_runs (task_id),
    patient_id      text NOT NULL,
    night_date      date NOT NULL,
    verdict         text NOT NULL,
    explanation     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Mock gold serving tables (semops plan §4.3): what Spark's gold sync will write; filled from scenario YAML for now.
-- Derived data, rebuildable; the worker only reads them.
CREATE SCHEMA IF NOT EXISTS vitals;

CREATE TABLE IF NOT EXISTS vitals.sync_batches (
    batch_id        text PRIMARY KEY,
    schema_version  integer NOT NULL DEFAULT 1,
    source          text NOT NULL,             -- e.g. scenarios:<n files>; later the lakeFS commit
    night_from      date NOT NULL,
    night_to        date NOT NULL,
    status          text NOT NULL CHECK (status IN ('staged', 'committed', 'rejected')),
    staged_at       timestamptz NOT NULL DEFAULT now(),
    committed_at    timestamptz
);

-- One row per patient-night: the night's values. Missing data stays NULL.
CREATE TABLE IF NOT EXISTS vitals.nightly_features (
    patient_id        text NOT NULL,
    night_date        date NOT NULL,
    rhr               double precision,
    hrv_sdnn          double precision,
    wrist_temp_delta  double precision,
    resp_rate         double precision,
    spo2_mean         double precision,
    steps             double precision,
    batch_id          text NOT NULL REFERENCES vitals.sync_batches (batch_id),
    PRIMARY KEY (patient_id, night_date)
);

-- One row per patient-night-signal for the signals the patient has a baseline for: how far from the baseline.
CREATE TABLE IF NOT EXISTS vitals.nightly_deviations (
    patient_id      text NOT NULL,
    night_date      date NOT NULL,
    signal          text NOT NULL,
    baseline_median double precision NOT NULL,
    baseline_mad    double precision NOT NULL,
    z               double precision,                      -- NULL when the value is missing
    coverage        double precision NOT NULL DEFAULT 1,
    batch_id        text NOT NULL REFERENCES vitals.sync_batches (batch_id),
    PRIMARY KEY (patient_id, night_date, signal)
);

CREATE INDEX IF NOT EXISTS nightly_deviations_by_signal ON vitals.nightly_deviations (signal, night_date, z);

-- Why a night was flagged (L1 rules, red flag, L2 score). A row = an alert candidate for the pipeline.
CREATE TABLE IF NOT EXISTS vitals.nightly_flags (
    patient_id   text NOT NULL,
    night_date   date NOT NULL,
    l1_reasons   text[] NOT NULL DEFAULT '{}',
    red_flag     boolean NOT NULL DEFAULT false,
    l2_score     double precision,
    batch_id     text NOT NULL REFERENCES vitals.sync_batches (batch_id),
    PRIMARY KEY (patient_id, night_date)
);

-- Descriptive context (semops plan §4.6), later from db_lord / FHIR. Conditions, medications and notes in one table.
CREATE SCHEMA IF NOT EXISTS patient_context;

CREATE TABLE IF NOT EXISTS patient_context.profiles (
    patient_id  text PRIMARY KEY,
    birth_year  integer NOT NULL,
    sex         text NOT NULL
);

CREATE TABLE IF NOT EXISTS patient_context.entries (
    entry_id    integer PRIMARY KEY,
    patient_id  text NOT NULL REFERENCES patient_context.profiles (patient_id),
    kind        text NOT NULL CHECK (kind IN ('condition', 'medication', 'encounter', 'note')),
    ts          timestamp,                     -- NULL for standing facts (a known condition)
    text        text NOT NULL
);

CREATE INDEX IF NOT EXISTS entries_by_patient ON patient_context.entries (patient_id, ts);
