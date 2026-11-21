CREATE SCHEMA IF NOT EXISTS worker;

CREATE TABLE IF NOT EXISTS worker.suspicious_events (
    event_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id   text NOT NULL,
    night_date   date NOT NULL,
    reasons      text,
    red_flag     boolean NOT NULL DEFAULT false,
    features     jsonb NOT NULL DEFAULT '{}',

    state        text NOT NULL DEFAULT 'pending'
                 CHECK (state IN ('pending', 'processing', 'finished', 'failed')),
    attempts     integer NOT NULL DEFAULT 0,
    run_after    timestamptz NOT NULL DEFAULT now(),
    locked_by    text,
    locked_until timestamptz,
    result       jsonb,
    explanation  text,
    error        text,

    created_at   timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz,

    UNIQUE (patient_id, night_date)
);

CREATE INDEX IF NOT EXISTS suspicious_events_open
    ON worker.suspicious_events (run_after, event_id)
    WHERE state IN ('pending', 'processing');

CREATE TABLE IF NOT EXISTS worker.patient_context (
    context_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id text NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('profile', 'medication', 'encounter', 'diary')),
    ts         timestamptz,
    text       text NOT NULL
);

CREATE INDEX IF NOT EXISTS patient_context_patient ON worker.patient_context (patient_id, ts);
