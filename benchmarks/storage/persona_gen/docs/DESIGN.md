# Synthetic persona generator: design

Design notes for the `persona_gen` package (`persona_gen/src/persona_gen/`). Setup, modes, data sources, assumptions and open work are in the [README](../README.md). The generator writes a storage-neutral Parquet dataset once, and storage candidates then load that dataset.

## Purpose and scope

The generator simulates wearable records for storage and query benchmarks. Wearable-only and clinical modes use the same behaviour, physiology, device and delivery layers. Clinical mode can simulate effects such as a decrease in heart rate after a beta-blocker start.

Ground rules:

- **Continuous time.** Behaviour is a timeline of intervals and physiology is evaluated at the timestamps each device requests, so there is no fixed grid and cost scales with records emitted.
- **Truth and observations stay separate,** and every observation is traceable to its device and its truth row.
- **Storage-neutral record model.** Tables carry a patient ID. Observations also carry device and wearable identifiers.
- **Determinism and provenance.** Output is deterministic per persona, parameters are versioned with provenance, and the dataset is generated once and loaded many times.

**Deduplication.** Neither platform removes duplicates from raw reads. HealthKit merges overlapping sources only in statistics queries; Health Connect dedupes by app priority in its aggregate API, and only for activity and sleep. The generator therefore emits overlapping records from every source as stored, with source and device fields intact. (I still have to test actual HealthKit and Health Connect behavior)

## Architecture

```text
persona_gen/src/persona_gen/
  params/        versioned TOML: population, behavior, physiology, clinical, cohorts,
                 devices, platforms, delivery, references
  config.py      load + deep-merge overlays, provenance enforcement, SHA-256 of the set
  rng.py         SeedSequence(seed, spawn_key=(persona, *hashed names)) streams
  persona/       joint sampler, cohorts, anchors (twins/variants), Synthea CSV reader,
                 clinical backbone (conditions, medications, procedures)
  behavior/      events (illness, travel, injury, mood episodes, hospitalization),
                 day planner + semi-Markov fill, sleep architecture, workout templates
  physiology/    daily latent state + trajectories, continuous HR (kinetics, dose
                 curves, OU noise), beat-to-beat HRV
  devices/       ownership timeline, wear + signal quality, per-device contexts and
                 measurement policies, derived metrics, workouts, manual logging
  delivery/      created_at (native vs companion batching), app enrollment + sync,
                 Health Connect history window
  output/        Arrow schemas and the Parquet shard writer
  dataset.py     read a dataset back, verify checksums
  sources/       readers and converters for the real exports (HealthKit XML, LifeSnaps BSON, Parquet)
  calibration/   export and LifeSnaps profilers, overlay writers, Zepp fit
  validation/    structure, behaviour, statistics, effects, shape-vs-export reports
  simulate.py    one persona end to end
  api.py         SyntheticRecipe, generate_dataset (shards, workers), estimate_rows
```

Days are built from fixed blocks plus semi-Markov fill:

- **Work:** office, manual, student, or rotating early/late/night shifts. After a night shift the main sleep is in the morning, and a nap comes before the first night.
- **Other fixed blocks:** commutes, structured workouts, travel, and naps. Garmin, Oura, Samsung and Fitbit detect naps; the Apple Watch does not.

Behavior is a gap-free sequence of intervals with arbitrary start and end times. Heart rate is a function evaluated exactly at whatever timestamps a device requests, and cumulative quantities (steps, distance, energy) are integrated exactly over each record's interval. Loops in Python run per behavior interval (about 80 a day); sampling, integration and noise are vectorized with numpy.

## Record model

Each table carries `patient_id`. Observations also carry `device_id`, which is the physical hardware and changes on upgrade, and `wearable_id`, which identifies the logical wearable, survives hardware upgrades, and is null for phone records. A synthetic marker can be injected into any of these at load time.

| Table | Content |
| --- | --- |
| `observations` | One row per platform record. `metric`, `unit`, `value` or `category`, `start`/`end` (UTC, whole seconds as in the exports), `start_offset_min`/`end_offset_min`, `created_at` (HealthKit creationDate), `source_name`, `device_model`, `platform`, `truth_kind` + `truth_seq` (trace to ground truth), `readable` (Health Connect history rule), `duplicate_of` (re-sends). |
| `workouts` | Observed workout records: activity, recorded window, energy, distance, effort, auto-detected flag, link to the truth workout. |
| `truth_intervals` | The behavior timeline: state, activity, MET, cadence, speed, HR target and start value, outdoors, upright. |
| `truth_days`, `truth_nights`, `truth_workouts`, `truth_hrv`, `truth_wear` | Latent daily state, sleep sessions, intended workouts, true RR-window HRV, off-wrist spans and their reasons. |
| `events` | Labelled ground truth: condition onset, medication start/stop and doses, illness, travel, injury, mood episodes, hospitalization, upgrades, abandonment, platform switch. |
| `personas`, `devices`, `app_sync` | Attributes (cohort, anchor, traits, clinical lists), device periods, our app's sync sessions. |
| `routes` | GPS points (about 1 Hz) for outdoor recorded walks, runs, rides and hikes. Linked to `workouts` by `device_id` and `truth_workout`. |
| `ecg` | On-demand single-lead ECG recordings: 30 s at 512 Hz in µV, with Apple-style classification and average HR. |

Large tables are partitioned as `shard=NNNNN/month=YYYY-MM`. A daily partition would create tens of thousands of tiny files. The other tables are partitioned by `shard` only. Files use zstd with dictionary encoding, and rows are ordered by patient, then time. The manifest records the recipe, parameter versions and digest, per-file SHA-256 and row counts, observation rows per persona-year by device archetype, and throughput (in `run`, which is not part of the logical dataset).

## Parameters

Each table in `params/*.toml` needs `source = "<assumption|calibrated|reference|platform|spec>: detail"`, and nested tables inherit their parent's label. `load_params()` rejects unlabelled values.

Overlays are TOML files with `[meta] target = "<file>"` that deep-merge into the base set; the dataset digest covers the overlays too. Order: base files, bundled overlays from `params/defaults/`, the fitted Zepp overlay (when fitted defaults are enabled), then caller overlays in the order supplied. `[meta] replace = ["dotted.path"]` clears the named tables before merging any overlays in that set. Overlays for local comparisons (your own device cadences or anchors) can live under `.local/calibration/` and are git ignored.

**Anchor sets.** The anchor share defaults to 0, so standard fixtures use sampled traits. A local comparison opts in with `twins=True` or a nonzero `cohorts.anchors.share` overlay; the first persona indices then correspond to the selected profiles. The bundled set (`params/defaults/anchors-lifesnaps.toml`) is a stopgap until the population calibration lands: 8 LifeSnaps participants picked by k-medoids (`sources/lifesnaps_bson.py`), each a Fitbit Sense with an Android phone, with per-person medians as traits. LifeSnaps age is only `<30`/`>=30` (mapped to 25/40). Resting HR and breathing rate are shifted by the measured `fitbit_sense` readout bias so the twins' device values match the real summaries. To recalibrate (1-2 minutes, reads the 9.7 GB dump without pymongo):

```python
from pathlib import Path
from persona_gen.calibration import calibrate_lifesnaps

calibrate_lifesnaps(
    Path("Sample_Health_data/Fitbit/rais_anonymized/mongo_rais_anonymized/fitbit.bson"),
    profile_dir=Path(".local/calibration"),  # writes params/defaults/ by default
)
```

`write_lifesnaps_overlays(profile, out_dir, k=...)` rewrites the overlays from an existing profile JSON.

**Device measurement error.** `[signal]` in `devices.toml` holds shared defaults, and a model overrides any key in its own `[models.<name>.signal]` table (inherited through `extends`). Keys cover HR noise, motion-scaled error and outliers, cadence lock, SpO₂ bias and spread, HRV bias and spread (log scale), active-energy bias and noise, and day-to-day step error. Sleep-stage confusion matrices and step bias are per model. All of these are assumptions (see the README).

## Mode selection and clinical precedence

`persona-gen generate --personas N --days D --out DIR` defaults to plain wearable-only; `--wearable-only` makes the selection explicit. Wearable-only fixtures have empty condition, medication and inpatient timelines and skip clinical cohorts. There are two variants:

| Variant | Switch | Events |
| --- | --- | --- |
| Plain (default) | none | No colds, injuries, mood episodes or travel. Day-to-day variation comes from the routine, day-level and wear models only. Device events such as hardware upgrades still occur |
| With everyday events | `--events` | Colds, injuries, mood episodes and travel are ordinary simulated events |

The library switch is `SyntheticRecipe(everyday_events=...)`: `None` (default) lets the mode decide, `True` adds the events to a wearable-only run, and `False` is the explicit plain choice. Clinical (Synthea) and anchor runs always have everyday events, so `False` is refused there and `--events` is refused with `--synthea`. The manifest of a wearable-only dataset records `everyday_events` at the top level; clinical and anchor manifests are unchanged, and explicit local anchor comparisons are labelled `anchor_comparison`. Persona traits and devices are drawn from separate random streams, so the two variants have the same personas and devices for the same seed; only the event-driven days differ.

`--synthea DIR` enables clinical mode (the README describes how to produce a roster; the library takes `synthea_dir`):

- Synthea sets age at the window start, sex, mapped conditions, prescriptions and overlapping inpatient stays. Conditions and prescriptions are mapped to supported effects in `clinical.toml`. Consecutive refills of the same medication class can form one course.
- Clinical cohort shares determine which eligible patients are preferred. An unavailable cohort falls back to an eligible general cohort patient, and the manifest reports the roster digest. The generator fails when a requested assignment has neither pool available, and records reuse after a pool is exhausted.
- Clinical overlays can change effect parameters and cohort weights. Synthea still supplies the history, including stays that begin before the generation window. Behaviour, physiology traits, devices and everyday events are sampled around that history.
- Seeded assignments are stable across shards. Clinical mode requires anchor share zero and disables twins.

### Limits of Synthea

Synthea's disease progressions are idealized: rule-based modules with textbook courses, no real-world variation in onset, adherence or treatment response, and conditions that never interact with how the person actually moves or sleeps. Its prevalence is also off for some conditions (coronary heart disease is far too common in older patients, ADHD rises with age where real data falls, depression and bipolar are nearly absent, and sleep apnea falls after 60-70), which is why the fallback sampler only uses it for five conditions. It has no wearable signals, so everything physiological comes from the generator's own medication and condition effects in `clinical.toml`.

## Library usage

```python
from datetime import date
from pathlib import Path
from persona_gen import SyntheticRecipe, estimate_rows, generate_dataset, open_dataset

recipe = SyntheticRecipe(start=date(2026, 1, 1), days=365, personas=1_000, seed=42)
print(estimate_rows(recipe))  # pilot-based size estimate before a large run
if __name__ == "__main__":  # workers use the spawn start method
    manifest = generate_dataset(
        Path(".local/personas/y2026-1k"),
        recipe,
        personas_per_shard=250,
        workers=8,
    )
    dataset = open_dataset(manifest)
    dataset.verify()
```

Loaders call `open_dataset(manifest)` and stream `Dataset.batches("observations")`, or read the Parquet files with DuckDB or PyArrow.

Rough volume (Nov 2026, local VM with 4 cores): a native-watch persona writes ~1.1M rows per persona-year, a companion-app persona ~0.25M, a phone-only persona ~0.08M; throughput is 0.45-0.5M observations/s per worker. An Apple Watch Series 12 adds about 17k heart-rate rows per day from the upgrade date. `SyntheticRecipe(metrics=(...))` caps density.

## Calibration and validation workflow

Run from the workspace root. Set `BENCH_LIFESNAPS_BSON`, `BENCH_KAGGLE_CSV` and `BENCH_HEALTH_ARCHIVE` to the input files. Each conversion writes a fresh directory under `.local/calibration/`. The clinical example also needs a Synthea CSV roster in `.local/synthea/csv`.

```sh
uv run persona-gen convert-calibration lifesnaps "$BENCH_LIFESNAPS_BSON" .local/calibration/raw/lifesnaps
uv run persona-gen convert-calibration kaggle "$BENCH_KAGGLE_CSV" .local/calibration/raw/kaggle
uv run persona-gen adapt-calibration lifesnaps .local/calibration/raw/lifesnaps .local/calibration/observed/lifesnaps
uv run persona-gen adapt-calibration kaggle .local/calibration/raw/kaggle .local/calibration/observed/kaggle
uv run persona-gen adapt-calibration apple "$BENCH_HEALTH_ARCHIVE" .local/calibration/observed/apple
uv run persona-gen fit-lifesnaps-device .local/calibration/lifesnaps_bson.profile.json .local/calibration/fitbit-training.toml
uv run persona-gen generate --personas 100 --days 28 --kaggle-csv "$BENCH_KAGGLE_CSV" \
  --out .local/personas
uv run persona-gen generate --personas 100 --days 28 --kaggle-csv "$BENCH_KAGGLE_CSV" \
  --synthea .local/synthea/csv --out .local/personas-clinical
uv run persona-gen validate-storage --real .local/calibration/observed/kaggle \
  --device zepp_amazfit --fixture .local/personas --fixture .local/personas-clinical \
  --out .local/results/zepp-storage.json
```

- **Conversion:** one Parquet table per LifeSnaps source type, split by participant, with checksummed manifests and a verified read-back. The Kaggle CSV is converted with row-group checks against a fresh parse. Apple tarballs are streamed directly.
- **Adapters** emit the observation schema plus `source_fields` (original locators). Units are canonical, step counts are interval increments, repeat payloads are kept and counted, and missing delivery timestamps stay null. Fitbit wall time goes in the timestamp columns with null UTC offsets and a local-clock marker.
- **Splits:** LifeSnaps is split by participant (training-only overlay and fixtures per split seed; the report checks the training-set fingerprint in the fixture manifest). Apple and Kaggle use a date holdout (`--holdout-start`; Kaggle defaults to 2025-01-01). Real-vs-real baselines give the spread; deviations above the 95th percentile of those differences are flagged.
- **Per-device checks:** generate enough personas to cover each model, and isolate a model with an ownership-weight overlay. Comparisons against the personal exports are retrospective, since their fitting windows are not proven disjoint.
- **Zepp overlay:** fitted from pre-2025 Kaggle rows (HR cadence, step and energy intervals, sleep staging, write delays); the cache key is the CSV digest, fit version and training cutoff. `persona-gen fit-zepp-overlay --force` refits.
- **Dynamics:** `calibration/lifesnaps.py` produces `[spread]` and `[dynamics]` in `references.toml`, and `validation.dynamics_report` compares synthetic wearable users against them. `calibration.calibrate` fits private comparison overlays from local archives.
- **Twin plots and explorer:** `validation.plots.plot_twin(...)` (needs the `plots` extra) and `notebooks/twin_explorer.py` (`cd persona_gen && uv run --extra notebook marimo edit notebooks/twin_explorer.py`).

## Data coverage

The generator models every data type that appears in at least one source (the two Apple Health exports or LifeSnaps) and also exists in HealthKit or Health Connect, apart from the gaps listed under "Not modeled". Canonical metric names and platform identifiers live in `params/platforms.toml`; a metric without an identifier on a platform is never emitted there.

### Modeled

| Group | Metrics | Devices |
| --- | --- | --- |
| Cardiac | heart rate, resting HR (derived from the device's own samples), walking HR average, HR recovery, HRV SDNN, HRV RMSSD (only where the platform and device write it), VO2max | Watches, ring, trackers |
| Respiration and vitals | respiratory rate, SpO2, wrist temperature, sleeping breathing disturbances | Apple Watch (feature-gated), Samsung (assumption) |
| Activity | steps, walking/running distance, cycling distance, active and basal energy, physical effort, flights climbed, exercise minutes, stand hours and stand time, time in daylight | Watch and phone (phone only while carried) |
| Gait | walking speed, step length, double support, asymmetry | iPhone |
| Running dynamics | running speed, power, stride length, ground contact time, vertical oscillation | Apple Watch, outdoor recorded runs |
| Sleep | in bed, awake, core, deep, REM, unspecified (confusion-matrix staging with fragmentation) | Watches, ring |
| Workouts | walk, run, intervals, cycle, strength, micro sets, HIIT, yoga, swim, hike; recorded, auto-detected or incidental; effort score | Watches, trackers |
| Audio | environmental and headphone exposure, environmental audio exposure events (> 80 dB for 3 min) | Watch, iPhone |
| Body and BP | body mass, BMI, body fat, blood pressure | Smart scale, manual entry, cuff |
| Nutrition | energy, protein, carbohydrates, fat, saturated fat, fiber, sugar, cholesterol, sodium, potassium, calcium, iron, magnesium, zinc, vitamins C, D, B12, water, caffeine | Rare nutrition-logging personas |
| Lifestyle | alcoholic beverages, height | Rare loggers, Health profile |
| Rhythm and ECG | AFib burden (weekly, AFib History), on-demand ECG waveforms (`ecg` table) | iPhone + Apple Watch |
| Mobility | walking steadiness, six-minute-walk estimate (weekly), stair ascent and descent speed | iPhone, Apple Watch |
| Routes | GPS tracks of outdoor recorded workouts (`routes` table) | Apple Watch, Garmin |

### Not modeled

| Group | Types |
| --- | --- |
| In the exports but not modeled | headphone audio notifications, walking-steadiness notification events, rarely logged micronutrients (iodine, selenium, chromium, molybdenum, biotin, ...) |
| In HealthKit/Health Connect but in no source | cycle tracking, glucose, body temperature, mindfulness, handwashing, audiograms, electrodermal activity, spirometry, symptoms |
| Fitbit-only (LifeSnaps) | readiness/stress scores, mood and survey data, other study fields without a platform type |
