# Local stack (Docker Compose)

Runs the Wearables platform on one machine without Kubernetes. Service configuration mirrors the Helm charts in `gitops/`; Traefik exposes the same public paths as production.

- [What has been verified](#what-has-been-verified)
- [Deploying on a single developer machine](#deploying-on-a-single-developer-machine)
- [Team setup: every developer runs the stack locally](#team-setup-every-developer-runs-the-stack-locally)
- [Endpoints](#endpoints)
- [Sending data](#sending-data)
- [Troubleshooting](#troubleshooting)
- [Known gaps](#known-gaps)

## What has been verified

Tested end to end on 2026-10-23 (Apple Silicon Mac, Docker Desktop with 8 GB RAM / 8 CPUs), using `data-generator/generate.py`:

| Stage | Status | Evidence |
|---|---|---|
| Web login → create case → case token (wearables-bff) | ✅ | case created from hospital case `C-123456`, token issued |
| Patient creation in db_lord (through the BFF) | ✅ | patient visible at `GET /api/patients/<id>` and in the UI |
| Traefik → importservice (`/import/ingest`, JWT check) | ✅ | HTTP 200; `patientId` from the token replaces `deviceId` |
| Kafka `wearables-raw` → FHIR mapper → `wearables-lp` | ✅ | every record sent was mapped, `dlq` stayed empty |
| Telegraf → InfluxDB (`measurements` bucket) | ✅ | 10 measurement types written, tagged with `device-id=<patientId>` |
| Extraction API (`/api/extraction/v1/...`) | ✅ | readings returned for the patient |
| Grafana embed through grafana-proxy (case page) | ✅ | "General data" tab shows the patient's heart rate |
| Spark raw → bronze → silver (Delta on SeaweedFS / lakeFS) | ✅ | all three streaming jobs run |
| MLflow model → predictions → `ml_predictions` bucket | ⚠️ | predictions are written, but without a patient tag (see [Known gaps](#known-gaps)) |

Not verified yet:

- The "Six minute walking test" and "AI Insights" Grafana tabs.
- Device and wearable management in db_lord (`/devices`, `/cases/{id}/wearables/...`). The ingestion pipeline keys data by patient only, so these endpoints are not part of the tested flow.
- The production login flow: outside `NODE_ENV=production` the BFF logs users in directly and sends no magic link mail.
- Full FHIR validation coverage. The mapper only validates every 100th resource (`VALIDATION_FREQUENCY=100`), and only the types the generator sends were exercised.
- The real iPhone app against this stack.

## Deploying on a single developer machine

### Requirements

| Resource | Core stack | Core + `ml` profile |
|---|---|---|
| Docker memory | 4 GB | 8 GB (measured: ~6.9 GB in use) |
| Free Docker disk | ~15 GB | ~25 GB |
| Free host ports | 80, 3003, 5432, 8000, 8086, 8088, 29092 | + 5001, 6566, 8001, 8333 |

Docker Desktop: *Settings → Resources* sets memory and the disk limit. The disk is shared with every other project on the machine; `docker system df` shows what is using it.

### Start

```bash
cd deploy/local
docker compose up -d --build               # core platform (first build: ~5-10 min)
docker compose --profile ml up -d --build  # optional: Spark / lakeFS / SeaweedFS / MLflow / Feast
docker compose ps                          # one-shot *-init / keygen / ml-train services exit with 0
```

Defaults work without a `.env` file. To override secrets or ports, `cp .env.example .env` and edit it.

### Day-to-day

```bash
docker compose logs -f importservice fhir-mapper-validator telegraf   # follow the pipeline
docker compose up -d --build wearables-bff                           # rebuild one service after a code change
docker compose --profile ml stop                                     # free ~4 GB RAM when ML is not needed
docker compose --profile ml down                                     # stop everything, keep data
docker compose --profile ml down -v                                  # stop everything and delete all data
```

There is no hot reload in containers. For fast frontend/BFF iteration, run them on the host (`npm --prefix services/web run dev`, see the root README) and keep the rest in Docker.

### Machine-specific notes (Apple Silicon, 8 GB Docker)

- With the `ml` profile running, memory is nearly exhausted. Stop the profile when you only work on ingestion, the BFF or the frontend.
- The Docker disk filled up to 100% during the first ML build, and apt inside the build then failed with `invalid signature`. `docker builder prune -af` frees the build cache. Volumes and images of other projects are left for you to clean up.
- The Docker VM clock can lag the Mac after sleep. The generator therefore backdates its locally signed tokens by 60 s (see [Troubleshooting](#troubleshooting)).

## Team setup: every developer runs the stack locally

Each developer runs their own copy of the stack; nothing is shared between machines. To keep setups identical:

1. **Use this compose file as the single source of local configuration.** Change `docker-compose.yml` and the files next to it through pull requests, not ad-hoc local edits, so everyone gets the same fixes.
2. **Personal overrides go into `.env`, which is git-ignored.** Typical overrides: `ADMIN_EMAILS` (your own address) and host ports that clash on your machine. Add every new variable to `.env.example` with a working default.
3. **The secrets here are for local use only** (`JWT_SECRET=dev-secret`, the Influx token, lakeFS sample keys). Never reuse them on a shared or public server.
4. **Data is per machine.** Volumes live in each developer's Docker. Reproduce test data with the generator (`--seed` makes runs deterministic) instead of sharing database dumps; real participant data must never be loaded into a local stack.
5. **Architecture:** images are built locally, so Apple Silicon (arm64) and x86 machines both work. The first build downloads Maven, npm, pip and Spark dependencies and needs network access.
6. **Phone testing:** a developer's phone reaches only their own machine. Use a personal tunnel (`cloudflared tunnel --url http://localhost:80`) and pass the URL to the app with `--dart-define=INGEST_ENDPOINT=...`. iOS signing changes (team, bundle id) stay local and must not be committed.
7. **Before reporting a bug,** reproduce it on a clean stack with `docker compose --profile ml down -v && docker compose up -d --build`, and include `docker compose ps` plus the logs of the failing service.

A shared, always-on environment (for example a team test server) should be deployed with the Helm charts in `gitops/` instead of this compose file. That requires real secrets, TLS and persistent user storage.

## Endpoints

| URL | Service |
|---|---|
| http://localhost | Clinician frontend (`services/web`) |
| http://localhost/api | wearables-bff (registration/auth, case tokens) |
| http://localhost/api/extraction/docs | Extraction API (Swagger) |
| http://localhost/import/ingest | importservice (mobile app upload target) |
| http://localhost/proxy | grafana-proxy (dashboard embedding) |
| http://localhost:3003/proxy/ | Grafana admin (admin / admin); embedded dashboards go through `/proxy` |
| http://localhost:8088 | Traefik dashboard |
| http://localhost:8000/docs | db_lord REST + GraphQL |
| http://localhost:8086 | InfluxDB UI (admin / admin-password) |
| localhost:29092 | Kafka for host clients |
| localhost:5432 | Postgres (postgres / postgres) |
| http://localhost:5001 | MLflow tracking + model registry (`ml` profile) |
| http://localhost:8001 | lakeFS UI (`ml` profile, keys in `.env.example`) |
| localhost:8333 | SeaweedFS S3 (`ml` profile) |
| localhost:6566 | Feast feature server (`ml` profile) |

### Logging in

Outside production, the BFF logs an `ADMIN_EMAILS` address in directly when you submit it on the login page; no mail is sent. Users and sessions live in BFF memory, so restarting `wearables-bff` logs everyone out.

### Test patients

Cases are created from hospital case ids. The hospital lookup is mocked in `services/backend/wearables-bff/src/mockData.ts`, so only these ids exist: `C-123456`, `C-654321`, `C-000000`, `C-000001`, `C-000010`, `C-000100`, `C-001000`, `C-010000`. Creating a case also creates the patient in db_lord; its patient id is shown in the UI.

## Sending data

### Data generator (no phone needed)

`data-generator/generate.py` uses only the Python standard library and sends the same payload shape as the iPhone app: heart rate, respiratory rate, HRV, steps, distance, energy and sleep stages.

```bash
# Data for an existing patient (shows up on the case page in the UI)
python3 data-generator/generate.py --patient-id <patient-id-from-ui> --backfill-hours 6 --live 60

# Or use the case token itself (QR code content)
python3 data-generator/generate.py --token <case-token> --backfill-hours 24
```

`--patient-id` signs a token with `JWT_SECRET`. Any id is accepted, but only ids of patients created through the UI appear in the web app.

### iPhone app

iOS requires HTTPS, so expose the stack through a tunnel:

```bash
cloudflared tunnel --url http://localhost:80     # or: ngrok http 80
cd services/mobile/mobile_app
flutter run -d <device-id> --dart-define=INGEST_ENDPOINT=https://<tunnel-host>/import/ingest
```

Then create a case in the web UI and scan its QR code with the app.

### Data flow

App or generator → importservice → Kafka `wearables-raw` → fhir-mapper-validator → Kafka `wearables-lp` → Telegraf → InfluxDB → db_lord → BFF / extraction / Grafana.

With the `ml` profile, Spark also reads `wearables-lp`: bronze (Delta on SeaweedFS) → silver (Delta on lakeFS branch `processed`) → Feast → MLflow model → InfluxDB bucket `ml_predictions`. `ml-train` registers a demo model (`heart_rate_model@Production`) trained on synthetic data. The silver and prediction jobs restart until their upstream Delta tables exist.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 Invalid or expired token`; importservice logs `issued in the future` | Docker VM clock behind the host | Retry; the generator backdates tokens by 60 s. Restarting Docker Desktop resyncs the clock |
| `401 Invalid issuer` | `TOKEN_ISSUER` (BFF) ≠ `JWT_ISSUER` (importservice) | Both are `wearables-bff` in this compose file |
| Grafana iframe shows "Page not found" | Grafana sub path ≠ proxy path | `GF_SERVER_ROOT_URL` must end in `/proxy/` (already set) |
| Build fails with apt `invalid signature` | Docker disk full | `docker builder prune -af`; raise the Docker disk limit |
| SeaweedFS `no free volumes left` | Default 30 GB volume size | Already lowered via `-master.volumeSizeLimitMB=256` |
| `lakefs-init` loops with `401` | lakeFS admin not set up | `lakefs-init` calls `/api/v1/setup_lakefs` on first start; on an old volume run `docker compose --profile ml down -v` |
| Logged out after a restart | BFF keeps users in memory | Log in again |

## Known gaps

Found while testing this stack; these need development work rather than local configuration:

1. **Patient id lost in the ML pipeline.** The mapper writes only `device-id-reference=Patient/<id>` to `wearables-lp`; Telegraf patches in `device-id`, but `bronze_to_silver.py` parses `device-id=` and gets an empty string. Predictions have no patient and Feast entities collapse into one.
2. **Hospital cases are mocked.** `findHospitalCase` always reads `mockData.ts`, even with `USE_MOCK_DATA=false`.
3. **No persistent user database.** BFF users, roles, approvals, sessions and API tokens are in-memory maps.
4. **Inconsistent Influx tags.** db_lord's `patient_id` / `case_id` filters find nothing because the data carries only `device-id`. extraction-service works around it. Case-to-device assignments in db_lord are not used by the pipeline.
5. **Demo ML model.** `ml_flow_training.py` trains on random data.
