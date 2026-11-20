# persona-gen

Synthetic wearable persona generator: simulates people, routines, physiology, devices and the delivery of
data from device to platform, and writes Parquet. Ground truth and device observations are separate tables,
linked by `truth_kind`/`truth_seq`.

**Status:** It runs end to end and has tests, but parts are unfinished (see
[Limitations and open work](#limitations-and-open-work)). It tries to be realistic but is not real
clinical data. Parameters come from public datasets, a few private personal exports, published studies and labelled assumptions; each value has a `source` label.

Originally started to generate datasets for testing storage and query performance of different dbs, but then it mutated into this.

Architecture, record model and parameter rules are in [docs/DESIGN.md](docs/DESIGN.md).

## Modes

| Mode | Selected by | Content |
| --- | --- | --- |
| Wearable-only, plain (default) | no flag | Routines and devices only: no conditions, medications, hospital stays, colds, injuries, mood episodes or travel |
| Wearable-only with events | `--events` | Plain, plus colds, injuries, mood episodes and travel |
| Clinical | `--synthea DIR` | People, conditions, medications and stays from a Synthea roster, plus everyday events |

## Quick start

Run from `benchmarks/storage/` (the uv workspace root):

```sh
uv sync --all-packages --all-extras
uv run persona-gen generate --personas 100 --days 28 --out .local/personas
uv run persona-gen generate --personas 100 --days 28 --synthea .local/synthea/csv --out .local/personas-clinical
uv run persona-gen generate --personas 1000 --days 365 --estimate   # row-count estimate only
uv run persona-gen --help
```

Library API: [`src/persona_gen/api.py`](src/persona_gen/api.py) and [`src/persona_gen/dataset.py`](src/persona_gen/dataset.py).

Output is Hive-partitioned Parquet plus a manifest.
Schemas are in `src/persona_gen/output/schema.py`. Output is deterministic for a given recipe, parameters and code version. The manifest records the parameter values per file.

## Clinical mode: Synthea

Needs `patients.csv`, `conditions.csv`, `medications.csv` and `encounters.csv` from a
[Synthea](https://github.com/synthetichealth/synthea) run (Java 17+). Run it with `persona_gen.persona.synthea.run_synthea`, or pass any directory containing the four CSVs to `--synthea`. Set `reference` to
the start of the generation window. Generate at least as many patients as personas per cohort; otherwise patients
are reused and the persona is flagged `synthea_reused`. Conditions and medications map to generator classes by
regex in `params/clinical.toml`.

## Calibration data

| Source | Used for | Handling |
| --- | --- | --- |
| [LifeSnaps](https://www.kaggle.com/datasets/skywescar/lifesnaps-fitbit-dataset) | Population spread and day-to-day dynamics, Fitbit device timing, eight comparison anchors | `params/references.toml` and `params/defaults/` |
| [Kaggle Apple Health export](https://www.kaggle.com/datasets/pacific28/apple-health-data) | Zepp/Amazfit cadence and delivery, an independent iPhone comparison | `generate` fits the Zepp model from the CSV and caches it under `<cache root>/calibration/generated/` |
| Private Apple Watch and Garmin exports (one person each) | Native-watch cadence, companion-app write lag | Aggregate timings only; labelled "Person A/B" in `params/*.toml` |
| Synthea roster | Age-band prevalence of hypertension, type 2 diabetes, atrial fibrillation, heart failure and COPD in the fallback condition sampler | `python -m persona_gen.calibration.synthea_prevalence DIR`; diagnosed prevalence, not survey-measured |
| Published studies | Device error, medication effects, some baselines | Relevant studies are named in `source` labels; most values are just assumptions |
| Platform docs | Release dates, type availability, history limits, dedup rules | `params/platforms.toml` |

Download the public data with `Sample_Health_data/*/download.sh` (Kaggle CLI, credentials may be needed; LifeSnaps
is about 9 GB). The datasets keep their own licences (LifeSnaps CC BY 4.0, Kaggle export CC BY-NC-SA 4.0); see
their Kaggle pages. The default CSV lookup searches the working directory and its parents. With fitted
defaults enabled, `generate` uses a cached Zepp overlay if the CSV is absent. If both are absent, it warns
and omits the Zepp model, so fixtures made without the CSV have no Zepp devices. The manifest lists applied overlays.

| Environment variable | Effect |
| --- | --- |
| `PERSONA_GEN_FITTED_DEFAULTS=0` | Same as `--no-fitted-defaults` |
| `PERSONA_GEN_HOME` | Cache root (then `BENCH_HOME`, then `.local`) |
| `PERSONA_GEN_KAGGLE_CSV` | Path of the Kaggle CSV (or `--kaggle-csv`) |

## Tests

```sh
uv run --locked --all-packages --all-extras python -m pytest persona_gen/tests
uv run --locked --all-packages --all-extras ruff check persona_gen
uv run --locked --all-packages --all-extras ty check persona_gen
```

Tests need no downloaded data. Some write large temp files; set `TMPDIR` if the temp volume is small.

## Assumptions

- **Most parameter values are best guesses ("vibes"), and many were AI-generated.** Only the `calibrated:` tables
  were computed from data (LifeSnaps, the Synthea roster, the Apple Health and Garmin exports). Everything else in
  `src/persona_gen/params/*.toml` is labelled `assumption:`: plausible values written by an AI assistant, with a
  paper or link named where one informed them. The papers are context, not a source of the exact numbers, and the
  values were extracted by ai and havent been veriefied. They need to be replaced/ adjusted with actual, factual values (see
  [open work](#limitations-and-open-work)).
- No real Health Connect data was used: Android write policies, history limits and app priorities (Fitbit,
  Samsung, Pixel, Oura, Withings) are assumptions. Fitbit timing comes from Fitbit Web API data, not from what
  Fitbit writes to Health Connect.
- Device measurement error is loosely based on published validation studies, but the exact values are still
  assumptions. The calibration data has no True label / reference ECG or sleep study.
- Overlapping records from several sources are emitted as stored, not deduplicated.
- Phone carry, sleep-stage confusion, medication and illness effect sizes, Zepp iOS share (0.05), charging and
  step bias are all vibes-based assumptions (see `source` labels).
- In the plain variant, gaps and level changes have no modelled cause.
- No persona is a real participant. Anchor twins are synthetic personas calibrated to the median steps and sleep
  of individual LifeSnaps participants. Anchors are off by default (anchor share 0).

## Limitations and open work

Open items are also marked `TODO` / `TODO(realism)` in the code.

**Known issues**

- Anchor twins' median daily steps land 30-45% off `daily_steps_target`; the `_calibrate_twin` pilot in
  `simulate.py` does not seem to carry over. Cause not found.
- Apple Watch cadence and Garmin write lag come from one person each; Samsung, Pixel and Fitbit sleep-stage
  matrices are extrapolated from one Fitbit model.
- Not modelled: per-wearer HR bias (the umbrella review, doi 10.1007/s40279-024-02077-2, cites a mean Fitbit bias of
  -3.39 bpm, Chevance et al.), timestamp lag errors, sustained dropouts, SpO₂ error at low saturation, device-level
  energy error, the app version timeline. HRV and SpO₂ are unvalidated.
- HRV (SDNN) reference bands and coronary heart disease and psychiatric prevalence tables use assumed values.
  The fallback sampler uses Synthea prevalence for the five conditions listed in [Calibration data](#calibration-data).
- The workout-day share is lower than LifeSnaps by design (LifeSnaps counts Fitbit's auto-recognised activity), so
  `dynamics_workout_day_share` fails.
- Routes are a random walk near home (not even following streets / real routes). osmnx would give real streets.
- Validation uses one seed and 28-90 day windows.
- Real exports are re-parsed from the archives on every run (an export XML can exceed 2 GB), which also slows the
  explorer notebook.

**Planned work**

- **Sources:** one shared Parquet layout for the Apple Health exports and Kaggle records; explorer notebook reading it.
- **Devices:** companion-app write lag fit (backfill share, heavy tail), phone-versus-wearable step overlap, iPhone
  check, real Fitbit writes into Health Connect if data turns up.
- **Population and intraday:** fit trait distributions, correlations and day-level dynamics, then retire the
  LifeSnaps anchors; activity profiles, workouts, sleep stages and exercise HR from LifeSnaps.
- **Parameters:** fit or source assumed values and quantify their effect on simulated steps, heart rate, HRV, sleep,
  prevalence and medication effects through sensitivity runs and validation checks.
- **Validation:** write-lag and cross-source overlap shares, real-vs-real baselines by period, multiple seeds,
  sequence and clinical-event checks, HRV/SpO₂.
