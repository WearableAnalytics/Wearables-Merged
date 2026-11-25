# Adding to the worker

New behaviour goes into a **stage**. The loop (`worker.py`) and the queue (`repository.py`) should rarely change, which
keeps two people working on different stages out of each other's way.

## What a stage looks like

```python
class MyStage:
    name = "my_stage"

    def run(self, ctx: Context, conn: Connection) -> dict:
        ...
        return {"anything": "json-serialisable"}
```

- `ctx.event` is the claimed row (read-only): patient, night, reasons, red flag, pipeline features.
- `ctx.patient` holds the patient context loaded by `load_context`, grouped by kind.
- `ctx.result` holds the outputs of earlier stages; what you return is stored under `ctx.result[name]` and ends up in
  the `result` column.
- Set `ctx.explanation` if your stage produces the text clinicians read. Set `ctx.stop = True` to skip the stages after
  yours.
- `conn` is an autocommit connection for reads. Do not commit, and do not touch `state`; the worker does that.

Then register it in `default_stages()` in `llm_worker/stages/__init__.py`, put new settings in `settings.py` and the
README table, and add tests.

## Workflow

1. Write the test first. Stage logic gets a plain unit test in `tests/test_stages.py` (fake `sleep`, no database).
   Anything that reads tables goes into an integration test that uses the `conn` fixture.
2. Make it pass, keep `ruff check` and `ruff format --check` clean.
3. One milestone per PR, branched from `feat/llm-worker-skeleton`.

## Rules that already hold for the real worker

- A red-flag event never goes through the semantic filter and can never be marked as explained.
- A stage must be safe to run twice on the same event; a lease can expire and the event is processed again.
- Patient context only from the night itself or earlier, never from the future.
- Nothing sent to an LLM contains `patient_id`.
