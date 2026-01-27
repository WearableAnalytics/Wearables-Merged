CREATE TABLE "patients" (
  "id" uuid PRIMARY KEY,
  "charite_id" uuid NOT NULL,
  "name" varchar NOT NULL,
  "sex" varchar,
  "dob" date,
  "weight" numeric(6,2),
  "height" numeric(4,2)
);

CREATE TABLE "devices" (
  "id" uuid PRIMARY KEY,
  "serial_nr" varchar NOT NULL,
  "model" varchar NOT NULL,
  "manufacturer" varchar,
  "os_version" varchar NOT NULL
);

CREATE TABLE "wearables" (
  "id" uuid PRIMARY KEY,
  "serial_nr" varchar NOT NULL,
  "model" varchar NOT NULL,
  "manufacturer" varchar,
  "os_version" varchar NOT NULL
);

CREATE TABLE "cases" (
  "id" uuid PRIMARY KEY,
  "status" varchar NOT NULL,
  "patient_id" uuid NOT NULL
);

CREATE TABLE "contexts" (
  "id" uuid PRIMARY KEY,
  "group_name" varchar NOT NULL,
  "coordinator" varchar
);

CREATE TABLE "case_contexts" (
  "case_id" uuid NOT NULL,
  "context_id" uuid NOT NULL,
  PRIMARY KEY ("case_id", "context_id")
);

CREATE TABLE "case_devices" (
  "case_id" uuid NOT NULL,
  "device_id" uuid NOT NULL,
  "assigned_from" timestamp NOT NULL,
  "assigned_to" timestamp,
  PRIMARY KEY ("case_id", "device_id", "assigned_from")
);

CREATE TABLE "case_wearables" (
  "case_id" uuid NOT NULL,
  "wearable_id" uuid NOT NULL,
  "assigned_from" timestamp NOT NULL,
  "assigned_to" timestamp,
  PRIMARY KEY ("case_id", "wearable_id", "assigned_from")
);

CREATE TABLE "influx_measurements" (
  "case_id" uuid,
  "patient_id" uuid,
  "wearable_id" uuid,
  "device_id" uuid,
  "wearable_firmware" varchar,
  "phone_os_version" varchar,
  "app_version" varchar,
  "unit" varchar,
  "code" varchar,
  "system" varchar,
  "time" timestamp,
  "heart_rate_bpm" float,
  "spo2_percent" float,
  "steps_count" int,
  "other_meassurments" float,
  "ml_anomaly_score" float
);

CREATE UNIQUE INDEX ON "devices" ("serial_nr");

CREATE UNIQUE INDEX ON "wearables" ("serial_nr");

CREATE INDEX ON "cases" ("patient_id");

CREATE INDEX ON "case_devices" ("device_id");

CREATE INDEX ON "case_wearables" ("wearable_id");

ALTER TABLE "cases" ADD FOREIGN KEY ("patient_id") REFERENCES "patients" ("id");

ALTER TABLE "case_contexts" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id");

ALTER TABLE "case_contexts" ADD FOREIGN KEY ("context_id") REFERENCES "contexts" ("id");

ALTER TABLE "case_devices" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id");

ALTER TABLE "case_devices" ADD FOREIGN KEY ("device_id") REFERENCES "devices" ("id");

ALTER TABLE "case_wearables" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id");

ALTER TABLE "case_wearables" ADD FOREIGN KEY ("wearable_id") REFERENCES "wearables" ("id");

ALTER TABLE "influx_measurements" ADD FOREIGN KEY ("case_id") REFERENCES "cases" ("id");

ALTER TABLE "influx_measurements" ADD FOREIGN KEY ("patient_id") REFERENCES "patients" ("id");

-- makes sure that a device can only be actively assigned to one case at a time
CREATE UNIQUE INDEX "unique_active_device_assignment" 
ON "case_devices" ("device_id") 
WHERE "assigned_to" IS NULL;

CREATE UNIQUE INDEX "unique_active_wearable_assignment" 
ON "case_wearables" ("wearable_id") 
WHERE "assigned_to" IS NULL;
