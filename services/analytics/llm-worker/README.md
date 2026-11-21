# llm-worker

Picks up suspicious events from PostgreSQL, runs them through a small pipeline and writes the result back:

```
pending ─claim─▶ processing ─▶ load_context ─▶ semantic_filter ─▶ explain ─▶ finished ─▶ notify
                     │                (red flags skip the filter)
                     └─ a stage raises ─▶ back to pending with backoff ─▶ failed after the last attempt
```

Today every stage is a stand-in: `semantic_filter` and `explain` sleep for a while and `explain` writes a template
explanation. They have the same shape as the real L3 semantic filter and L4 explanation, so each one can be swapped for
the real thing without touching the loop. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Run it

```bash
docker compose up --build                                   # postgres, schema migration, one worker
docker compose run --rm migrate python -m llm_worker seed   # 5 events for 3 patients, one red flag
docker compose logs -f worker                               # one "finish event N" + "[notify]" per event
```

More workers: `docker compose up --scale worker=3`. Each event is processed by exactly one of them.

Look at the results:

```bash
docker compose exec postgres psql -U worker -d worker \
  -c "SELECT event_id, state, attempts, result, explanation FROM worker.suspicious_events"
```

## Run it locally (no container for the worker)

The worker only needs a PostgreSQL. The default `WORKER_DSN` points at the one from this compose file on port 55433:

```bash
docker compose up -d postgres        # or any PostgreSQL you have: export WORKER_DSN=postgresql://user:pw@host:port/db
```

With [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run python -m llm_worker migrate  # create the schema (safe to run again)
uv run python -m llm_worker seed     # sample events and patient context
uv run python -m llm_worker run      # keep consuming; Ctrl-C finishes the current event, then stops
```

With plain Python (3.12 or newer):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m llm_worker migrate
python -m llm_worker seed
python -m llm_worker run
```

`python -m llm_worker once` processes everything that is pending and exits. For quick runs, shorten the fake work with
`WORKER_WORK_SECONDS=1`. Add an event by hand:

```bash
docker compose exec postgres psql -U worker -d worker -c "
  INSERT INTO worker.suspicious_events (patient_id, night_date, reasons, features)
  VALUES ('p-001', '2026-03-20', 'rule:multi_signal', '{\"rhr_z\": 2.6}')"
```

Clean up with `docker compose down -v`.

## Settings

| Variable | Default | |
| --- | --- | --- |
| `WORKER_DSN` | `postgresql://worker:worker@localhost:55433/worker` | database (the compose postgres) |
| `WORKER_ID` | hostname | written to `locked_by` |
| `WORKER_WORK_SECONDS` | `10` | fake work per event, split between filter and explain |
| `WORKER_POLL_INTERVAL_SECONDS` | `2` | wait when the queue is empty |
| `WORKER_LEASE_SECONDS` | `60` | after this, an unfinished event can be claimed again |
| `WORKER_MAX_ATTEMPTS` | `3` | then the event is `failed` |
| `WORKER_BACKOFF_SECONDS` | `5` | retry delay, doubled on every attempt |

## How it behaves

- **No double processing.** Claims use `SELECT … FOR UPDATE SKIP LOCKED`, so workers never block each other or take the
  same row.
- **Crashes.** A claimed event carries a lease. If the worker dies, another one takes the event after the lease runs out.
  A worker that lost its lease can no longer write to the row.
- **Failures.** An exception in a stage sends the event back to `pending` with exponential backoff and stores the error.
  After `WORKER_MAX_ATTEMPTS` it becomes `failed`. An event whose lease keeps expiring is failed the same way.
- **Shutdown.** `SIGTERM` lets the current event finish, then the worker exits. `docker compose stop` waits up to 30 s.
- **Notification** goes out only after the result is committed, so whoever receives it can already read the explanation.

## Tests

```bash
uv run pytest            # needs Docker for the integration tests (throwaway postgres via testcontainers)
uv run pytest -m "not integration"
uv run ruff check . && uv run ruff format --check .
```
