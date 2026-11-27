# Adding to the worker

Keep changes in one of these places, so two people rarely touch the same file:

| You want to … | Change | Not |
| --- | --- | --- |
| change what the model is asked (triage rule, benign causes, explanation style) | `llm_worker/operators/*.yaml`, bump `version` | Python |
| add a test case / mock patient | `llm_worker/scenarios/<name>.yaml` | providers |
| plug in a real data source (PostgreSQL `vitals`, db_lord, ClickHouse) | a new class in `llm_worker/providers/` implementing `NumericContextProvider` or `DescriptiveContextProvider` | stages |
| add an operator kind (LOTUS `sem_agg`, `sem_topk`, …) | a new class with `@register_operator("<kind>")` | existing operators |
| add a pipeline step | a new stage in `llm_worker/stages/`, registered in `default_stages()` | `worker.py` |
| change what the model reads | `render.py`, bump `RENDER_VERSION` | operators |
| add a task template (a new kind of question) | a handler in `llm_worker/tasks/handlers/` with `@register_task` and its specs | `worker.py`, the router |
| add a demo question | `llm_worker/tasks/demo.py` | |

## What a stage looks like

Stages work on a whole claimed batch at once (LOTUS works on DataFrames):

```python
class MyStage:
    name = "my_stage"

    def run(self, batch: list[Context], conn) -> list[dict]:
        return [{"anything": "json-serialisable"} for ctx in batch]  # one output per candidate, same order
```

- `ctx.event` is the claimed queue row; `ctx.bundle` the evidence (DTOs from `dto.py`); `ctx.rendered` the text the
  operators read; `ctx.decision` / `ctx.explained` the L3 / L4 results.
- Set `ctx.error` to fail one candidate (it is retried on its own); raise to fail and retry the whole batch.
  `ctx.stop = True` skips the remaining stages for that candidate. `ctx.notify = False` holds the notification back.
- What you return is stored under `result[name]`. Do not commit and do not touch `state`; the worker does that.

## Workflow

1. Write the test first. Stage logic: `tests/test_stages.py` with a scripted operator (no model, no database).
   LOTUS plumbing: `tests/test_semantic.py` against `fake_llm`. Real model: `tests/test_ollama.py` (`-m ollama`).
2. Make it pass; keep `ruff check` and `ruff format --check` clean.
3. One milestone per PR, branched from `feat/semantic-task-worker`.

## Rules that hold everywhere

- A red flag never goes through triage and can never be suppressed.
- An answer the code cannot read never suppresses a notification.
- Context only from before `as_of_for(night)`, never from the future.
- Nothing sent to a model contains `patient_id` or other identifiers.
- Only a pipeline `alert_triage` task can notify; chat templates are read-only.
- Request text fills spec slots only; data scope comes from validated `params`.
- A stage must be safe to run twice on the same candidate; a lease can expire and the batch is processed again.
