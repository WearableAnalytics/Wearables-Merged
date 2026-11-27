# Services Overview

Overview of the services in the **Wearables** repository:

## Core Services

| Service | Purpose | Documentation |
|---|---|---|
| **Cloud Connector** | Cloud provider OAuth linking, webhooks and health data sync (e.g. garmin, polar, oura, google health) | [Cloud Connector Docs](cloud-connector/index.md) |
| **Mobile App** (`mobile_app`) | Flutter app collecting HealthKit or Health Connect data and managing cloud connections | *Coming soon* |
| **Import Service** (`importservice`) | FastAPI upload gateway validating JWTs and publishing uploads to Kafka | *Coming soon* |
| **FHIR Mapper + Validator** | Kafka Streams mapper converting `wearables-raw` into FHIR and InfluxDB line protocol (`wearables-lp`) | *Coming soon* |
| **Wearables BFF** (`wearables-bff`) | Backend-for-Frontend managing accounts, study cases and QR JWTs | *Coming soon* |
| **Web Frontend** (`web`) | React + Vite portal for clinical staff and participants | *Coming soon* |
| **db_lord** | Storage API (InfluxDB & PostgreSQL) | *Coming soon* |
| **Extraction Service** | Research data export API | *Coming soon* |
| **Grafana Proxy** (`grafana-proxy`) | Authenticated reverse proxy for embedded dashboards | *Coming soon* |
| **ML Pipeline** (`gitops/apps/ml-pipeline`) | Spark Structured Streaming (`wearables-lp` → SeaweedFS/LakeFS), Feast Feature Store, MLflow & KServe | *Coming soon* |
