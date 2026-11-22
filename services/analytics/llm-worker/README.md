# llm-worker

Picks up flagged patient-nights (alert candidates) from PostgreSQL and runs them, in batches, through semantic
operators (LOTUS) on a language model, then writes the decision and an explanation back:

```
pending ─claim ≤ 8─▶ processing ─▶ load_evidence ─▶ triage (sem_filter) ─▶ explain (sem_map) ─▶ finished ─▶ notify
                                     numbers + text     red flags skip it      every candidate       (not if suppressed)
                          └─ model down ─▶ whole batch back to pending with backoff ─▶ failed after the last attempt
```

- **load_evidence**: numbers (gold layer) and descriptive text (patient context) are fetched in parallel and rendered
  into two text columns. Every line carries an id (`n:rhr`, `c:104`) the model must cite.
- **triage** (L3): LOTUS `sem_filter` with a natural-language spec. True = a documented benign cause explains the night
  → `suppress`; false → `notify`; an unclear answer → `unparseable_notify`. Red flags never reach the model
  (`red_flag_bypass`).
- **explain** (L4): LOTUS `sem_map` writes a short note for the physician. Cited ids are checked against the evidence;
  unknown ids are dropped. An unusable answer falls back to a template (`fallback: true`).

Design and decisions: `docs/architecture/llm-worker-semops-plan.md` (main checkout).

### What is mocked

| Piece | Today | Later (plan) |
| --- | --- | --- |
| Gold layer numbers | scenario YAML files in `llm_worker/scenarios/` | `vitals` serving tables in PostgreSQL (§4) |
| Patient context | the same scenario files | `patient_context` schema, then db_lord / FHIR |
| Model | `fake-llm` (in compose), or local Ollama | Ollama / vLLM on the OpenStack cluster |
| Queue | `worker.suspicious_events` (state on the row) | `alerting.alert_candidates` + `triage_jobs` + result tables (S0) |

Only `NumericContextProvider` / `DescriptiveContextProvider` (`llm_worker/providers/`) and the three `WORKER_LLM_*`
settings change when the real pieces arrive.

## Run it

```bash
docker compose up --build                                   # postgres, migration, fake model, one worker
docker compose run --rm migrate python -m llm_worker seed   # one candidate per scenario (9, one red flag)
docker compose logs -f worker                               # "finish event N (verdict)" + "[notify]" lines
```

With a real model on your machine (Ollama):

```bash
ollama pull qwen2.5:7b
WORKER_LLM_BASE_URL=http://host.docker.internal:11434/v1 WORKER_LLM_MODEL=qwen2.5:7b docker compose up --build
```

With the cluster model: `kubectl -n bayes-llm port-forward svc/ollama 11434:11434`, then the same as above with the
cluster's model tag (to be confirmed with the platform team, plan §5.3).

Look at the results:

```bash
docker compose exec postgres psql -U worker -d worker -c "
  SELECT event_id, patient_id, state, result->'triage'->>'verdict' AS verdict, explanation
  FROM worker.suspicious_events ORDER BY event_id"
```

## Run it locally (no container for the worker)

```bash
docker compose up -d postgres
uv sync
uv run python -m llm_worker migrate
uv run python -m llm_worker seed
uv run python -m llm_worker fake-llm --port 8080 &          # or use Ollama (default URL: localhost:11434)
WORKER_LLM_BASE_URL=http://localhost:8080/v1 WORKER_LLM_MODEL=fake-small uv run python -m llm_worker once
```

`once` processes everything that is pending and exits; `run` keeps consuming until Ctrl-C. Python 3.12 only
(`lotus-ai 1.2.4` needs Python < 3.13, numpy < 2, pandas < 3).

## Ask a new question in plain language

Operators are specs written in natural language (`llm_worker/operators/*.yaml`), not code. Changing the clinical rule
means editing `triage.yaml` and bumping its `version` (stored with every result). The same engine answers ad-hoc
questions; this is the extension point for data scientists and clinicians later:

```python
from llm_worker.semantic import LotusModel, OperatorSpec, build_operator

question = OperatorSpec.adhoc("filter", "In {context}, the patient says they travelled to the mountains")
op = build_operator(question, columns={"numeric", "context"})
result = op(df, LotusModel(base_url="http://localhost:11434/v1", model="qwen2.5:7b"))  # df: rendered evidence
```

New operator kinds (LOTUS `sem_agg`, `sem_topk`, ...) are added with `@register_operator("agg")` in a new module,
without changing the existing ones. There is no API for this yet.

## Settings

| Variable | Default | |
| --- | --- | --- |
| `WORKER_DSN` | `postgresql://worker:worker@localhost:55433/worker` | database (the compose postgres) |
| `WORKER_ID` | hostname | written to `locked_by` |
| `WORKER_BATCH_SIZE` | `8` | candidates per claim = rows per LOTUS call |
| `WORKER_LLM_BASE_URL` | `http://localhost:11434/v1` | any OpenAI-compatible endpoint |
| `WORKER_LLM_MODEL` | `qwen2.5:7b` | model name on that endpoint |
| `WORKER_LLM_API_KEY` | `unused` | for a gateway that needs one |
| `WORKER_LLM_TIMEOUT_SECONDS` | `180` | per model call |
| `WORKER_LLM_CONCURRENCY` | `4` | parallel calls inside one LOTUS batch |
| `WORKER_SCENARIOS_DIR` | bundled | directory of scenario YAML files (mock data) |
| `WORKER_POLL_INTERVAL_SECONDS` | `2` | wait when the queue is empty |
| `WORKER_LEASE_SECONDS` | `900` | must cover a whole batch on a slow model |
| `WORKER_MAX_ATTEMPTS` | `3` | then the event is `failed` |
| `WORKER_BACKOFF_SECONDS` | `5` | retry delay, doubled on every attempt |

## How it behaves

- **Safety rules in code, not in the prompt:** red flags are never sent to the model and are always notified; an
  unclear triage answer notifies; citations are checked; nothing sent to the model contains `patient_id`; context is
  read only up to noon after the night (`providers.as_of_for`).
- **No double processing.** Claims use `SELECT … FOR UPDATE SKIP LOCKED … LIMIT n`.
- **Failures.** A model outage (`LLMUnavailable`) sends the whole batch back with backoff. A candidate without evidence
  fails on its own. After `WORKER_MAX_ATTEMPTS` the event is `failed`.
- **Notification** goes out only after the result is committed, and not for `suppress`.

## Tests

```bash
uv run pytest                       # unit + integration (Docker for a throwaway postgres); LOTUS runs against fake-llm
uv run pytest -m "not integration"  # no Docker
uv run pytest -m ollama -s          # real model through LOTUS; prints a per-scenario table (~5 min with qwen2.5:7b)
uv run ruff check . && uv run ruff format --check .
```

The `ollama` tests assert only what the code guarantees. Judgement quality depends on the model and is measured on the
cluster model; with qwen2.5:7b (2026-11-21) triage matched 5–6 of 8 scenarios and wrongly suppressed
`future_note_leak`.
