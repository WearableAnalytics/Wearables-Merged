# llm-worker: semantic task worker

Runs **tasks** with semantic operators (LOTUS) on a language model. A suspicious event from the data pipeline is one
kind of task; a question from a physician or data scientist in the chat is another. Both go through the same queue,
the same worker and the same operators:

```
pipeline event ─► alert_triage    (priority 0)  ─┐                    ┌─► answer + result (tasks.task_runs)
                                                 ├─► tasks.task_runs ─┤
chat question ─► router ─► patient_explain (10) ─┤   claim by priority └─► tasks.notifications (alert_triage only)
                       └─► cohort_query    (10) ─┘   → handler of the template → providers → render → LOTUS → model
```

| Template | Who may start it | Reads | Semantic operators | Side effect |
| --- | --- | --- | --- | --- |
| `alert_triage` | pipeline only | one patient-night: numbers + context | `sem_filter` (triage) → `sem_map` (explanation) | notifies unless suppressed |
| `patient_explain` | chat, pipeline | one patient, last N nights | nights that differ (\|z\| ≥ 1, no model) → `sem_map` per night → `sem_agg` | none |
| `cohort_query` | chat | every patient, one anonymous row each | `sem_filter` with the criterion → `sem_map` per match | none |

**Data comes from the database.** The numbers are read from mock gold serving tables in PostgreSQL (`vitals.nightly_features`,
`nightly_deviations`, `nightly_flags`, `sync_batches`; semops plan §4.3) and the context from `patient_context`
(`profiles`, `entries`). `load-mock` fills them from the scenario YAML as one committed batch; the real gold sync will
write the same tables. `cohort_query` takes an optional exact numeric predicate (`filters`, e.g. `wrist_temp_delta z >= 2`)
that runs as SQL before the model sees anything. Every result carries `evidence`: the nights and context it is based on,
straight from the tables (never from model output). The page shows them as a heatmap (z against the personal baseline,
cells the model cited outlined) with hover details for every cell and cited id.

Rules: permissions belong to the template, not to the trigger. `params` choose the data; the question text only fills
the semantic slot of a spec (`<<question>>`, `<<criterion>>`) and can never reference a column or widen the scope. Only a
pipeline `alert_triage` task can write a notification, whatever a handler returns (checked in `worker.py`).

## Requirements

| Dependency | Needed for | Notes |
| --- | --- | --- |
| Docker + Docker Compose v2 (`docker compose`) | the demo (`docker compose up`), and the integration tests (testcontainers starts a throwaway postgres) | Docker Desktop on macOS/Windows. The image is ~4.7 GB (LOTUS pulls in torch, CPU-only); allow ~10 GB free disk. Ports `127.0.0.1:8000` (web) and `127.0.0.1:55433` (postgres) must be free (`WORKER_WEB_PORT`, `WORKER_PG_PORT` to change). |
| Ollama (optional) | real answers from a local model | Without it the stack uses the bundled fake model (`fake-llm`): everything runs, answers are canned. With it: `ollama pull qwen2.5:7b` (~4.7 GB download, ~8 GB RAM; on an Apple Silicon laptop 15–100 s per chat question). Any OpenAI-compatible endpoint works instead (vLLM, the cluster model) via `WORKER_LLM_BASE_URL` / `WORKER_LLM_MODEL`. |
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | running the worker or the tests outside containers | `requires-python = ">=3.12,<3.13"`; `uv sync` installs the locked dependencies (`uv.lock`). Not needed for the compose demo. |

Ollama from inside the containers: the compose services reach the host as `host.docker.internal`. On Docker Desktop
this works with Ollama's default (listening on `127.0.0.1:11434`). On Linux, start Ollama with
`OLLAMA_HOST=0.0.0.0:11434` so the containers can reach it through the Docker bridge. Check with
`curl http://localhost:11434/v1/models`.

Answer quality with `qwen2.5:7b` is weak (several wrong triage verdicts, low cohort recall): it shows the plumbing
works, it is not an evaluation. Quality is to be measured on the cluster model.

## Demo

```bash
docker compose up --build              # postgres, migration, fake model, worker, web
open http://localhost:8000             # "Simulate pipeline", then ask in the chat (example buttons)
```

With the real model on your machine (Ollama):

```bash
ollama pull qwen2.5:7b
WORKER_LLM_BASE_URL=http://host.docker.internal:11434/v1 WORKER_LLM_MODEL=qwen2.5:7b docker compose up --build
```

Without containers for the worker:

```bash
docker compose up -d postgres
uv sync && uv run python -m llm_worker migrate && uv run python -m llm_worker load-mock
uv run python -m llm_worker web &      # http://localhost:8000
uv run python -m llm_worker run        # default model: Ollama qwen2.5:7b on localhost:11434
```

Two pools (clinical path isolated from chat questions): run one worker with `WORKER_TEMPLATES=alert_triage` and one
with `WORKER_TEMPLATES=patient_explain,cohort_query`.

### Mock data

14 patients in `llm_worker/scenarios/*.yaml` (one file per patient, numbers written by hand, each tests one behaviour),
data up to 2026-03-14. Described by age band and sex only. Highlights: P-010 influenza getting worse over four nights
vs. P-011 a cold that resolves; P-009 a red flag; P-006 a note written after the night (must not be read); P-012 a new
beta-blocker; P-013 jet lag; P-014 stable, never flagged. Demo questions: `llm_worker/tasks/demo.py`.

## What is mocked

| Piece | Today | Later |
| --- | --- | --- |
| Gold layer numbers, patient context | PG serving tables filled from scenario YAML (`load-mock`) | filled by the Spark gold sync (`commit_batch`) |
| Pipeline | `POST /api/demo/pipeline` or `python -m llm_worker simulate` | bridge from `alerting.alert_candidates` |
| Chat | `index.html` + rule-based router | BayesPlatform / MCP tool selecting a template |
| Notification channel | `tasks.notifications` + a log line | clinician inbox |
| Identity | `submitted_by` from a drop-down | the user's identity, permission checks, audit |

## API

| Method | Path | |
| --- | --- | --- |
| `POST` | `/api/chat` | `{text, submitted_by: doctor\|ds, patient_id?, template?, filters?: [{signal, op, z}], match?}` → `{task_id, template, params, notice}`; 403 for `alert_triage` |
| `POST` | `/api/demo/pipeline` | one `alert_triage` task per flagged night (idempotent) |
| `GET` | `/api/tasks?trigger=pipeline\|chat`, `/api/tasks/{id}` | state, answer, result, spec versions, model |
| `GET` | `/api/notifications`, `/api/patients`, `/api/demo/prompts`, `/api/status` | |

## Settings

| Variable | Default | |
| --- | --- | --- |
| `WORKER_DSN` | `postgresql://worker:worker@localhost:55433/worker` | the compose postgres |
| `WORKER_TEMPLATES` | empty (all) | comma-separated templates this worker claims |
| `WORKER_BATCH_SIZE` | `8` | upper bound per claim (alert_triage 8, chat templates 1) |
| `WORKER_LLM_BASE_URL` / `WORKER_LLM_MODEL` | `http://localhost:11434/v1` / `qwen2.5:7b` | any OpenAI-compatible endpoint |
| `WORKER_LLM_CONCURRENCY` | `4` | parallel calls inside one LOTUS batch |
| `WORKER_LLM_TIMEOUT_SECONDS` | `180` | per model call |
| `WORKER_LEASE_SECONDS` / `WORKER_MAX_ATTEMPTS` / `WORKER_BACKOFF_SECONDS` | `900` / `3` / `5` | queue behaviour |
| `WORKER_WEB_HOST` / `WORKER_WEB_PORT` | `127.0.0.1` / `8000` | demo page |
| `WORKER_DATA_SOURCE` | `pg` | `pg` = serving tables; `scenarios` = YAML directly (no tables needed) |
| `WORKER_SCENARIOS_DIR` | bundled | mock data directory (input of `load-mock`) |

## Tests

```bash
uv run pytest                       # unit + integration (Docker for a throwaway postgres); LOTUS against fake-llm
uv run pytest -m "not integration"  # no Docker
uv run pytest -m ollama -s          # real model: triage table + the 10 demo prompts (WORKER_DEMO_REPORT=x.md)
uv run ruff check . && uv run ruff format --check .
```

`-m ollama` asserts only what the code guarantees (routing, read-only chat, red flags, citations, no errors); answer
quality is printed for a human to judge against each prompt's `expect`.
