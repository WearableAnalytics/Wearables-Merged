"""Project local source records onto the generated observation schema for comparison."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ..output.schema import SCHEMAS
from .healthkit_xml import HK, HKC, export_files, family, xml_entries
from .raw import LIFESNAPS_METRICS, atomic_directory, write_manifest

# TODO(realism): Add HRV and SpO2 adapters with device-specific units and cadence checks.
OBSERVATIONS = SCHEMAS["observations"].append(pa.field("source_fields", pa.string()))
HEALTHKIT = {
    "HeartRate": "heart_rate",
    "StepCount": "steps",
    "SleepAnalysis": "sleep",
    "ActiveEnergyBurned": "active_energy",
}
UNITS = {"heart_rate": "count/min", "steps": "count", "sleep": "", "workout": "s", "active_energy": "kcal"}
KAGGLE_HOLDOUT = date(2025, 1, 1)
SLEEP = {
    "inbed": "in_bed",
    "asleep": "asleep_unspecified",
    "asleepunspecified": "asleep_unspecified",
    "asleepcore": "asleep_core",
    "asleepdeep": "asleep_deep",
    "asleeprem": "asleep_rem",
    "awake": "awake",
}
FITBIT_STAGES = {
    "wake": "awake",
    "awake": "awake",
    "light": "asleep_core",
    "deep": "asleep_deep",
    "rem": "asleep_rem",
    "asleep": "asleep_unspecified",
    "restless": "restless",
}


def _table(columns: dict[str, list | pa.Array]) -> pa.Table:
    n = len(columns["record_id"])
    arrays = []
    for field in OBSERVATIONS:
        values = columns.get(field.name)
        if values is None:
            array = pa.nulls(n, field.type)
        elif pa.types.is_dictionary(field.type):
            array = pa.array(values, type=pa.string()).dictionary_encode()
        else:
            array = pa.array(values, type=field.type)
        arrays.append(array)
    return pa.Table.from_arrays(arrays, schema=OBSERVATIONS)


def _rows(rows: list[dict]) -> pa.Table:
    return _table({name: [row.get(name) for row in rows] for name in set().union(*(row.keys() for row in rows))})


def _wall(stamp: datetime | None) -> datetime | None:
    return stamp.replace(tzinfo=UTC) if stamp else None


def _life_files(root: Path, relative_path: str, kind: str) -> Iterator[pa.Table]:
    path = root / relative_path
    fields = ["patient_id", "source_offset", "start", "end"]
    fields += {"heart_rate": ["value"], "steps": ["value"], "sleep": ["stages"], "exercise": ["activity"]}[kind]
    for batch in pq.ParquetFile(path).iter_batches(columns=fields):
        batch = batch.filter(pc.call_function("and", [batch["start"].is_valid(), batch["end"].is_valid()]))
        if not len(batch):
            continue
        if kind in {"heart_rate", "steps"}:
            offset = pc.cast(batch["source_offset"], pa.string())
            n = len(offset)
            label = pa.scalar(kind, pa.string())
            yield _table(
                {
                    "record_id": pc.call_function("binary_join_element_wise", ["lifesnaps", offset, ":"]),
                    "patient_id": batch["patient_id"],
                    "source_name": pa.repeat(pa.scalar("Fitbit"), n),
                    "device_model": pa.repeat(pa.scalar("fitbit_sense"), n),
                    "platform": pa.repeat(pa.scalar("fitbit_web_api"), n),
                    "metric": pa.repeat(label, n),
                    "unit": pa.repeat(pa.scalar(UNITS[kind]), n),
                    "value": batch["value"],
                    "start": pc.cast(batch["start"], OBSERVATIONS.field("start").type, safe=False),
                    "end": pc.cast(batch["end"], OBSERVATIONS.field("end").type, safe=False),
                    "source_fields": pc.call_function(
                        "binary_join_element_wise", ['{"clock":"local","bson_offset":', offset, "}", ""]
                    ),
                }
            )
            continue
        rows = []
        for row in batch.to_pylist():
            key = f"lifesnaps:{row['source_offset']}"
            common = {
                "patient_id": row["patient_id"],
                "source_name": "Fitbit",
                "device_model": "fitbit_sense",
                "platform": "fitbit_web_api",
            }
            source = {"clock": "local", "bson_offset": row["source_offset"]}
            start, end = row["start"], row["end"]
            if end < start:
                continue
            if kind == "exercise":
                rows.append(
                    dict(
                        common,
                        record_id=key,
                        metric="workout",
                        unit="s",
                        value=(end - start).total_seconds(),
                        category=row["activity"],
                        start=_wall(start),
                        end=_wall(end),
                        source_fields=json.dumps(source),
                    )
                )
                continue
            # Retain the session record and the two source stage streams. Fitbit's short wake
            # annotations may overlap main stages. They are separate records in the comparison.
            rows.append(
                dict(
                    common,
                    record_id=key,
                    metric="sleep_session",
                    start=_wall(start),
                    end=_wall(end),
                    unit="",
                    source_fields=json.dumps(source),
                )
            )
            for i, stage in enumerate(row["stages"] or []):
                if not stage["start"] or not stage["seconds"] or stage["seconds"] <= 0:
                    continue
                a = stage["start"]
                level = stage["level"] or ""
                rows.append(
                    dict(
                        common,
                        record_id=f"{key}:{i}",
                        metric="sleep",
                        unit="",
                        category=FITBIT_STAGES.get(level, level),
                        start=_wall(a),
                        end=_wall(a + timedelta(seconds=stage["seconds"])),
                        source_fields=json.dumps(source | {"short": stage["short"], "level": level}),
                    )
                )
        if rows:
            yield _rows(rows)


def _kaggle_time(record: dict, prefix: str) -> datetime | None:
    day, clock, offset = (record[f"m_{prefix}{key}"] for key in ("Date", "Time", "TimeZone"))
    if not day or not clock or not offset:
        return None
    hour = int(clock[:2]) % 12 + (12 if clock.endswith("PM") else 0)
    return datetime.fromisoformat(f"{day}T{hour:02d}{clock[2:8]}{offset}")


def _apple_row(
    key: str,
    patient: str,
    model: str,
    metric: str,
    a: datetime,
    b: datetime,
    created: datetime | None,
    value: str | None,
    unit: str | None,
    fields: dict,
) -> dict:
    start_offset, end_offset = a.utcoffset(), b.utcoffset()
    if start_offset is None or end_offset is None:
        raise ValueError("Apple Health start and end timestamps require UTC offsets")
    category = None
    if metric == "sleep":
        label = (value or "").removeprefix("HKCategoryValueSleepAnalysis").lower()
        category = SLEEP.get(label, label) or None
        number = None
    elif metric == "workout":
        category, number = value, (b - a).total_seconds()
    else:
        expected = UNITS[metric]
        if unit != expected:
            raise ValueError(f"Unexpected unit {unit!r} for {metric}")
        number = float(value) if value else None
    return {
        "record_id": key,
        "patient_id": patient,
        "source_name": model,
        "device_model": model,
        "platform": "healthkit",
        "metric": metric,
        "unit": UNITS[metric],
        "value": number,
        "category": category,
        "start": a,
        "end": b,
        "created_at": created,
        "start_offset_min": int(start_offset.total_seconds() // 60),
        "end_offset_min": int(end_offset.total_seconds() // 60),
        "source_fields": json.dumps(fields),
    }


def _kaggle_records(root: Path) -> Iterator[pa.Table]:
    index = 0
    for batch in pq.ParquetFile(root / "records.parquet").iter_batches():
        rows = []
        for record in batch.to_pylist():
            index += 1
            metric = HEALTHKIT.get(record["type"])
            if not metric or not (a := _kaggle_time(record, "start")) or not (b := _kaggle_time(record, "end")):
                continue
            source = record["sourceName"]
            model = "zepp_amazfit" if source == "Zepp" else family(source, record["device"])
            if model not in {"zepp_amazfit", "iphone"}:
                continue
            rows.append(
                _apple_row(
                    f"kaggle:{index}",
                    "kaggle",
                    model,
                    metric,
                    a,
                    b,
                    _kaggle_time(record, "creation"),
                    record["value"],
                    record["unit"],
                    {"csv_row": index, "source_version": record["sourceVersion"]},
                )
            )
        if rows:
            yield _rows(rows)


def _personal_records(archive: Path, patient: str) -> Iterator[pa.Table]:
    rows = []
    found = False
    for kind, _, stream in export_files(archive):
        if kind != "health-xml":
            continue
        found = True
        for index, entry in enumerate(xml_entries(stream)):
            tag = entry.tag
            attrs = entry.attrib
            model = family(attrs.get("sourceName", ""), attrs.get("device"))
            if model not in {"apple_watch", "garmin", "iphone"}:
                continue
            short_type = attrs.get("type", "").removeprefix(HK).removeprefix(HKC)
            metric = "workout" if tag == "Workout" else HEALTHKIT.get(short_type) if tag == "Record" else None
            if not metric or not attrs.get("startDate") or not attrs.get("endDate"):
                continue
            rows.append(
                _apple_row(
                    f"{patient}:{index}",
                    patient,
                    model,
                    metric,
                    datetime.fromisoformat(attrs["startDate"]),
                    datetime.fromisoformat(attrs["endDate"]),
                    datetime.fromisoformat(attrs["creationDate"]) if attrs.get("creationDate") else None,
                    attrs.get("workoutActivityType") if metric == "workout" else attrs.get("value"),
                    attrs.get("unit"),
                    {"xml_entry": index, "source_version": attrs.get("sourceVersion")},
                )
            )
            if len(rows) == 32768:
                yield _rows(rows)
                rows.clear()
    if not found:
        raise ValueError("No Apple Health XML found in archive")
    if rows:
        yield _rows(rows)


def adapt_observations(source: str, src: Path, out: Path, *, participant: str = "personal") -> dict:
    """Write comparable local Parquet observations. Original source rows stay in the raw archive."""
    with atomic_directory(out) as root:
        parts: dict[str, int] = {}
        if source == "lifesnaps":
            manifest = json.loads((src / "manifest.json").read_text())
            jobs = (
                (item["path"], _life_files(src, item["path"], item["source_type"]))
                for item in manifest["files"]
                if item["source_type"] in LIFESNAPS_METRICS
            )
        elif source == "kaggle":
            jobs = iter([("records.parquet", _kaggle_records(src))])
        elif source == "apple":
            jobs = iter([("records.parquet", _personal_records(src, participant))])
        else:
            raise ValueError(f"Unknown adaptation source {source!r}")
        for name, tables in jobs:
            path = root / "observations" / name
            path.parent.mkdir(exist_ok=True, parents=True)
            count = 0
            with pq.ParquetWriter(path, OBSERVATIONS, compression="zstd") as writer:
                for table in tables:
                    writer.write_table(table)
                    count += table.num_rows
            parts[name] = count
        result = {"source": source, "rows": sum(parts.values()), "observations": parts}
        write_manifest(root, result)
    return result
