"""Storage-oriented comparisons over the shared observation columns."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq

from ..sources.lifesnaps_bson import device_overlay
from ..sources.observations import KAGGLE_HOLDOUT

# TODO(realism): Add sequence, event and clinical outcome validation across longer windows and more seeds.
# TODO: Add the share of records written more than 7 days late and the overlap share between sources, and
# real-versus-real baselines by time period for the personal exports and Kaggle.
LEVELS = (0.05, 0.5, 0.95)
QUANTILES = "[0.05, 0.5, 0.95]"
METRICS = ("heart_rate", "steps", "sleep", "workout", "active_energy")
DAILY_COLUMNS = (
    "records",
    "duplicate_rows",
    "observed_hours",
    "gap_s",
    "duration_s",
    "lag_s",
    "value",
    "with_lag",
    "negative_lag_rows",
    "categories",
)


def split_people(people: list[str], seed: int = 42) -> tuple[list[str], list[str]]:
    """Reserve one third of participants. Repeated comparisons resample only this holdout."""
    ordered = sorted(set(people))
    if len(ordered) < 5:
        raise ValueError("LifeSnaps holdout requires at least five participants")
    shuffled = np.random.default_rng(seed).permutation(ordered).tolist()
    n = max(2, len(shuffled) // 3)
    return sorted(shuffled[n:]), sorted(shuffled[:n])


def _split_version(train: list[str], seed: int) -> str:
    fingerprint = hashlib.sha256("\0".join(train).encode()).hexdigest()[:16]
    return f"training-only-seed{seed}-{fingerprint}"


def fit_lifesnaps_device(profile_path: Path, out: Path, *, seed: int = 42) -> dict:
    import tomli_w

    profile = json.loads(profile_path.read_text())
    train, holdout = split_people([p["id"] for p in profile["participants"]], seed)
    training = set(train)
    overlay = device_overlay({"participants": [p for p in profile["participants"] if p["id"] in training]})
    overlay["meta"]["version"] += "-" + _split_version(train, seed)
    out.parent.mkdir(exist_ok=True, parents=True)
    with out.open("xb") as stream:
        tomli_w.dump(overlay, stream)
    return {"training_people": len(train), "holdout_people": len(holdout), "seed": seed}


def _files(root: Path, name: str) -> list[str]:
    return [str(p) for p in sorted((root / name).rglob("*.parquet"))]


def _lifesnaps_files(root: Path) -> dict[str, list[str]]:
    """LifeSnaps output files each contain one participant. Read IDs from their footers."""
    parts: dict[str, list[str]] = defaultdict(list)
    for path in _files(root, "observations"):
        metadata = pq.read_metadata(path)
        for i in range(metadata.num_row_groups):
            group = metadata.row_group(i)
            if group.num_rows:
                column = next(
                    group.column(j) for j in range(group.num_columns) if group.column(j).path_in_schema == "patient_id"
                )
                stats = column.statistics
                if stats is None or not stats.has_min_max or stats.min != stats.max:
                    raise ValueError(f"Expected one LifeSnaps participant per file: {path}")
                parts[stats.min].append(path)
                break
    return dict(parts)


def _daily(
    root: Path,
    model: str,
    *,
    source: str,
    files: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
) -> list[tuple]:
    files = files if files is not None else _files(root, "observations")
    if not files:
        raise ValueError(f"No observation Parquet files under {root}")
    with duckdb.connect(
        config={
            "threads": "2",
            "autoload_known_extensions": "false",
            "preserve_insertion_order": "false",
            "max_temp_directory_size": "2GB",
        }
    ) as con:
        con.read_parquet(files, hive_partitioning=False).create_view("observations")
        con.execute(
            "create temp table selection as select ?::varchar as model, ?::date as since, ?::date as until",
            [model, since, until],
        )
        if source == "synthetic":
            if not (devices := _files(root, "devices")):
                return []
            con.read_parquet(devices, hive_partitioning=False).create_view("devices")
            con.execute("""
                create temp table matched_devices as
                select devices.* from devices, selection
                where devices.model = selection.model
                    or (selection.model = 'apple_watch' and starts_with(devices.model, 'apple_watch_'))
            """)
            device_filter = "device_id in (select device_id from matched_devices)"
        else:
            device_filter = "device_model = selection.model"
        con.execute("create temp table metrics as select unnest(?::varchar[]) as metric", [list(METRICS)])
        con.execute(f"""
            create temp table daily as
            with records as (
                select patient_id, device_id, metric, record_id, value, category, duplicate_of,
                    epoch(start) as stamp,
                    epoch(start) + 60 * cast(coalesce(start_offset_min, 0) as integer) as local_stamp,
                    epoch("end") - epoch(start) as duration_s, epoch(created_at) - epoch("end") as lag_s
                from observations, selection
                where {device_filter} and metric in (select metric from metrics)
                    and "end" >= start
            ), local as (
                select *, date '1970-01-01' + cast(floor(local_stamp / 86400) as integer) as day from records
            ), labelled as (
                select *, struct_pack(stamp := stamp, duration := duration_s, value := value, category := category)
                    as payload
                from local, selection
                where (since is null or day >= since) and (until is null or day < until)
            ), ordered as (
                select *, stamp - lag(stamp) over series as gap_s,
                    payload is not distinct from lag(payload) over series as same_payload
                from labelled
                window series as (partition by patient_id, device_id, metric, day
                                  order by stamp, duration_s, value, category, record_id)
            )
            select patient_id, day, metric, count(*) as records,
                count(*) filter (where duplicate_of is not null or same_payload) as duplicate_rows,
                count(distinct floor(local_stamp / 3600)) as observed_hours,
                approx_quantile(gap_s, {QUANTILES}) filter (where gap_s > 0) as gap_s,
                approx_quantile(duration_s, {QUANTILES}) as duration_s,
                approx_quantile(lag_s, {QUANTILES}) as lag_s,
                approx_quantile(value, {QUANTILES}) as value,
                count(lag_s) as with_lag, count(*) filter (where lag_s < 0) as negative_lag_rows,
                histogram(category) filter (where category is not null) as categories
            from ordered group by all
        """)
        if source == "synthetic":
            # Workouts are their own table in generated fixtures. Join device periods for the
            # model and use the recorded start offset for alignment with the real adapter.
            if paths := _files(root, "workouts"):
                con.read_parquet(paths, hive_partitioning=False).create_view("workouts")
                con.execute(f"""
                    insert into daily
                    with records as (
                        select w.patient_id, w.device_id, epoch(w.start) as stamp, w.duration_s, w.activity,
                            epoch(w.start) + 60 * cast(w.start_offset_min as integer) as local_stamp,
                            epoch(w.created_at) - epoch(w."end") as lag_s
                        from workouts w
                        where w.device_id in (select device_id from matched_devices)
                    ), ordered as (
                        select *, date '1970-01-01' + cast(floor(local_stamp / 86400) as integer) as day,
                            floor(local_stamp / 3600) as hour
                        from records
                    ), gaps as (
                        select *, stamp - lag(stamp) over (
                            partition by patient_id, device_id, day order by stamp) as gap_s
                        from ordered, selection
                        where (since is null or day >= since) and (until is null or day < until)
                    )
                    select patient_id, day, 'workout', count(*), 0, count(distinct hour),
                        approx_quantile(gap_s, {QUANTILES}) filter (where gap_s > 0),
                        approx_quantile(duration_s, {QUANTILES}), approx_quantile(lag_s, {QUANTILES}),
                        approx_quantile(duration_s, {QUANTILES}), count(lag_s), count(*) filter (where lag_s < 0),
                        histogram(activity) filter (where activity is not null)
                    from gaps group by patient_id, day
                """)
            bounds = """
                select distinct d.patient_id, cast(series.day as date) as day
                from matched_devices d, selection s, lateral generate_series(
                    greatest(date '1970-01-01' + cast(floor(epoch(d.start) / 86400) as integer), s.since),
                    least(date '1970-01-01' + cast(ceil(epoch(d."end") / 86400) - 1 as integer), s.until - 1),
                    interval 1 day
                ) series(day)
            """
        else:
            bounds = """
                select span.patient_id, cast(series.day as date) as day
                from (select patient_id, min(day) as first, max(day) as last from daily group by patient_id) span,
                     lateral generate_series(span.first, span.last, interval 1 day) series(day)
            """
        return con.execute(f"""
            with exposure as ({bounds}),
            published as (select distinct metric from daily)
            select exposure.patient_id, exposure.day, published.metric,
                coalesce(records, 0), coalesce(duplicate_rows, 0), coalesce(observed_hours, 0),
                gap_s, duration_s, lag_s, value, coalesce(with_lag, 0), coalesce(negative_lag_rows, 0), categories
            from exposure cross join published
            left join daily using (patient_id, day, metric)
            order by patient_id, day, metric
        """).fetchall()


def _distribution(values: list[float]) -> list[float]:
    return np.round(np.quantile(values, LEVELS), 4).tolist()


def _summarize(rows: list[tuple]) -> dict[str, dict]:
    by_metric: dict[str, list[tuple]] = defaultdict(list)
    for patient, day, metric, *stats in rows:
        by_metric[metric].append((patient, day, *stats))
    out: dict[str, dict] = {}
    for metric, items in sorted(by_metric.items()):
        counts = [r[2] for r in items]
        result = {
            "people": len({r[0] for r in items}),
            "person_days": len(items),
            "rows": sum(counts),
            "coverage_days": round(sum(n > 0 for n in counts) / len(items), 4),
        }
        for index, name in enumerate(DAILY_COLUMNS, 2):
            values = [r[index] for r in items if r[index] is not None]
            if name in {"with_lag", "negative_lag_rows", "duplicate_rows"}:
                result[name] = sum(values)
            elif name == "categories":
                categories: Counter[str] = Counter()
                for counts_by_label in values:
                    categories.update(counts_by_label)
                result[name] = dict(sorted(categories.items()))
            elif values and isinstance(values[0], list):
                # Each row contributes a day-level percentile. Equal day weights prevent
                # the densest devices or burst days from dominating the summary.
                median = np.round(np.median(values, axis=0), 4).tolist()
                result[name] = median
            else:
                result[name] = _distribution(values) if values else None
        out[metric] = result
    return out


def _features(summary: dict[str, dict]) -> dict[str, dict[str, float]]:
    wanted = ("records", "observed_hours", "gap_s", "duration_s", "lag_s", "value")
    return {
        metric: {"coverage_days": values["coverage_days"]}
        | {f"{k}_p50": values[k][1] for k in wanted if values[k] is not None}
        for metric, values in summary.items()
    }


def _differences(left: dict, right: dict) -> dict[str, dict[str, float]]:
    lhs, rhs = _features(left), _features(right)
    return {
        metric: {name: round(value - rhs[metric][name], 4) for name, value in features.items() if name in rhs[metric]}
        for metric, features in lhs.items()
        if metric in rhs
    }


def _baselines(rows: list[tuple], source: str, seed: int, repeats: int) -> tuple[dict, int]:
    rng = np.random.default_rng(seed)
    groups: dict[str | int, list[tuple]] = defaultdict(list)
    first = min(row[1] for row in rows)
    for row in rows:
        key = row[0] if source == "lifesnaps" else (row[1] - first).days // 7
        groups[key].append(row)
    keys = sorted(groups, key=str) if source == "lifesnaps" else sorted(int(k) for k in groups)
    if len(keys) < 2:
        return {}, 0
    deltas: dict[tuple[str, str], list[float]] = defaultdict(list)
    for _ in range(repeats):
        if source == "lifesnaps":
            order = rng.permutation(keys)
        else:
            # Block bootstrap each side of a chronological split. The two sides never
            # share a measurement day; resampling whole weeks retains weekly dynamics.
            mid = len(keys) // 2
            left, right = keys[:mid], keys[mid:]
            order = [*rng.choice(left, len(left)), *rng.choice(right, len(right))]
        mid = len(keys) // 2
        a, b = (_summarize([row for key in part for row in groups[key]]) for part in (order[:mid], order[mid:]))
        for metric, values in _differences(a, b).items():
            for field, delta in values.items():
                deltas[metric, field].append(abs(delta))
    result: dict[str, dict] = defaultdict(dict)
    for (metric, field), values in deltas.items():
        result[metric][field] = {"abs_delta_interval_p05_p50_p95": _distribution(values), "comparisons": len(values)}
    return dict(result), len(keys)


def storage_report(
    real: Path,
    synthetic: list[Path],
    model: str,
    *,
    holdout_start: date | None = None,
    seed: int = 42,
    repeats: int = 24,
) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    source = json.loads((real / "manifest.json").read_text())["source"]
    notes = [
        "Counts include repeated records; duplicates are flagged by resend label or repeated measurement payload.",
        "Observed hours count local hours with at least one record start. Gaps are positive within-day start gaps.",
        "Gap, duration, lag and value statistics are medians of within-day p05/p50/p95 estimates.",
    ]
    fit_version = None
    if source == "lifesnaps":
        if holdout_start is not None:
            raise ValueError("LifeSnaps uses participant holdout")
        files_by_person = _lifesnaps_files(real)
        train, held = split_people(list(files_by_person), seed)
        # Bounded queries, even for the full 9.7 GB source.
        observed = [
            row for patient in held for row in _daily(real, model, source=source, files=files_by_person[patient])
        ]
        fit_version = _split_version(train, seed)
        split = {
            "kind": "participant",
            "training_people": len(train),
            "holdout_people": len(held),
            "seed": seed,
            "fit_version": fit_version,
        }
        notes.append(
            "LifeSnaps timestamps are local and delivery is unavailable. Fitbit Web API density is a device-side "
            "reference for the simulated Health Connect writer."
        )
        notes.append(
            "The training fingerprint covers device timing. Bundled population references use the full cohort."
        )
    else:
        if holdout_start is None:
            if source != "kaggle":
                raise ValueError("Provide --holdout-start for a personal archive")
            holdout_start = KAGGLE_HOLDOUT
        if source == "kaggle" and holdout_start < KAGGLE_HOLDOUT:
            raise ValueError(f"Kaggle holdout must start on or after {KAGGLE_HOLDOUT}")
        split = {
            "kind": "date",
            "holdout_start": holdout_start.isoformat(),
            **({"training_end_exclusive": KAGGLE_HOLDOUT.isoformat()} if source == "kaggle" else {}),
        }
        if source == "apple":
            notes.append(
                "Personal comparisons are retrospective unless parameters were fitted using only pre-holdout data."
            )
        observed = _daily(real, model, source=source, since=holdout_start)
    if not observed:
        raise ValueError(f"No held-out {model} records under {real}")
    reality = _summarize(observed)
    baseline, units = _baselines(observed, source, seed, repeats)
    fixtures = []
    for path in synthetic:
        manifest = json.loads((path / "manifest.json").read_text())
        recipe = manifest["recipe"]
        first = date.fromisoformat(recipe["start"])
        # The recipe window is UTC, so drop boundary dates where offsets can truncate counts.
        trim = int(recipe["days"] > 2)
        generated = _daily(
            path,
            model,
            source="synthetic",
            since=first + timedelta(days=trim),
            until=first + timedelta(days=recipe["days"] - trim),
        )
        summary = _summarize(generated)
        delta = _differences(summary, reality)
        exceeds = {
            metric: [
                field
                for field, value in values.items()
                if field in baseline.get(metric, {})
                and abs(value) > baseline[metric][field]["abs_delta_interval_p05_p50_p95"][2]
            ]
            for metric, values in delta.items()
        }
        fixtures.append(
            {
                "seed": recipe["seed"],
                "mode": manifest.get("mode", manifest["clinical_source"]),
                "params_sha256": manifest["params"]["sha256"],
                "metrics": summary,
                "delta_to_real": delta,
                "above_real_vs_real_p95": {metric: fields for metric, fields in exceeds.items() if fields},
                "missing_synthetic_metrics": sorted(set(reality) - set(summary)),
                **(
                    {
                        "has_training_only_lifesnaps_overlay": any(
                            fit_version in version for version in manifest["params"]["versions"].values()
                        )
                    }
                    if fit_version is not None
                    else {}
                ),
            }
        )
    return {
        "source": source,
        "model": model,
        "split": split,
        "notes": notes,
        "real_measurement_dates": [min(r[1] for r in observed).isoformat(), max(r[1] for r in observed).isoformat()],
        "real": reality,
        "real_vs_real": baseline,
        "baseline_units": units,
        "baseline_unit": "participant" if source == "lifesnaps" else "seven_day_block",
        "synthetic": fixtures,
    }
