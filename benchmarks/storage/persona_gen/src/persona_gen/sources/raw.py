"""Local, lossless source archives with typed columns for validation."""

import hashlib
import json
import os
import shutil
import time
from collections import Counter, defaultdict
from collections.abc import Generator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import partial
from multiprocessing import get_context
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import quote

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .lifesnaps_bson import _decode, _documents, _fast_value, _header, index_participants

BATCH_ROWS = 32768
LOCAL_TIME = pa.timestamp("ms")
LIFESNAPS_METRICS = {"heart_rate", "steps", "sleep", "exercise"}
BSON_FIELDS = [
    ("patient_id", pa.string()),
    ("source_offset", pa.int64()),
    ("source_type", pa.string()),
    ("raw_bson", pa.large_binary()),
]
BOUNDS = [("start", LOCAL_TIME), ("end", LOCAL_TIME)]
STAGE = pa.struct([("start", LOCAL_TIME), ("seconds", pa.float64()), ("level", pa.string()), ("short", pa.bool_())])
BSON_SCHEMAS = {
    "heart_rate": pa.schema([*BSON_FIELDS, *BOUNDS, ("value", pa.float64())]),
    "steps": pa.schema([*BSON_FIELDS, *BOUNDS, ("value", pa.float64())]),
    "sleep": pa.schema([*BSON_FIELDS, *BOUNDS, ("stages", pa.list_(STAGE))]),
    "exercise": pa.schema([*BSON_FIELDS, *BOUNDS, ("activity", pa.string())]),
}
KAGGLE_COLUMNS = (
    "type",
    "sourceName",
    "sourceVersion",
    "unit",
    "m_creationDate",
    "m_creationTime",
    "m_creationTime_am_pm",
    "m_creationTimeZone",
    "m_startDate",
    "m_startTime",
    "m_startTime_am_pm",
    "m_startTimeZone",
    "m_endDate",
    "m_endTime",
    "m_endTime_am_pm",
    "m_endTimeZone",
    "value",
    "device",
)
KAGGLE_LICENSE = "CC BY-NC-SA 4.0"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def atomic_directory(out: Path) -> Generator[Path]:
    """Yield a temporary directory next to ``out`` and rename it to ``out`` on success. Raises ``FileExistsError`` if
    ``out`` exists.
    """
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(exist_ok=True, parents=True)
    temp = Path(mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        yield temp
        os.rename(temp, out)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def write_manifest(root: Path, manifest: dict) -> None:
    (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _local_time(stamp: str) -> datetime:
    # Fitbit timestamps are documented as local wall time even when a Z suffix is present.
    if "/" in stamp:
        return datetime.strptime(stamp, "%m/%d/%y %H:%M:%S")
    return datetime.fromisoformat(stamp).replace(tzinfo=None)


def _optional_time(stamp: str | None) -> datetime | None:
    if stamp:
        try:
            return _local_time(stamp)
        except ValueError:
            pass
    return None


def _bson_row(buf: bytes | memoryview, pos: int, size: int, offset: int) -> tuple[str, dict]:
    patient, kind, after = _header(buf, pos)
    row = {
        "patient_id": patient,
        "source_offset": offset,
        "source_type": kind,
        "raw_bson": bytes(buf[pos : pos + size]),
    }
    if kind in {"heart_rate", "steps"}:
        sample = _fast_value(buf, after, pos + size, b"bpm\x00" if kind == "heart_rate" else b"value\x00")
        if sample and (start := _optional_time(sample[0].decode())) is not None:
            row.update(start=start, end=start + timedelta(minutes=1) if kind == "steps" else start, value=sample[1])
    elif kind in {"sleep", "exercise"}:
        data = _decode(buf, pos + 4, pos + size)["data"]
        start = _optional_time(data.get("startTime"))
        if kind == "exercise":
            duration = data.get("duration")
            row.update(
                start=start,
                end=start + timedelta(milliseconds=duration) if start and duration else None,
                activity=data.get("activityName"),
            )
        else:
            levels = data.get("levels") or {}
            stages = [
                {
                    "start": _optional_time(stage.get("dateTime")),
                    "seconds": stage.get("seconds"),
                    "level": stage.get("level"),
                    "short": key == "shortData",
                }
                for key in ("data", "shortData")
                for stage in levels.get(key, [])
            ]
            row.update(start=start, end=_optional_time(data.get("endTime")), stages=stages)
    return kind, row


def _verified_file(path: Path, root: Path, rows: int) -> dict:
    if pq.read_metadata(path).num_rows != rows:
        raise ValueError(f"Parquet row-count mismatch in {path}")
    return {
        "path": path.relative_to(root).as_posix(),
        "rows": rows,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def _life_partition(src: Path, root: Path, job: tuple[int, list[tuple[int, int]]]) -> list[dict]:
    part, runs = job
    buffers: dict[str, list[dict]] = defaultdict(list)
    writers: dict[str, pq.ParquetWriter] = {}
    counts: dict[str, int] = defaultdict(int)
    digests = defaultdict(hashlib.sha256)
    paths: dict[str, Path] = {}

    def flush(kind: str) -> None:
        schema = BSON_SCHEMAS.get(kind, pa.schema(BSON_FIELDS))
        if kind not in writers:
            escaped = quote(kind, safe="")
            folder = root / (escaped if escaped not in ("", ".", "..") else "%" + kind.encode().hex())
            folder.mkdir(exist_ok=True)
            path = paths[kind] = folder / f"{part:03d}.parquet"
            writers[kind] = pq.ParquetWriter(
                path,
                schema,
                compression="zstd",
                use_dictionary=["source_type", "patient_id"],
                write_statistics=[name for name in schema.names if name != "raw_bson"],
            )
        writers[kind].write_table(pa.Table.from_pylist(buffers[kind], schema=schema))
        buffers[kind].clear()

    try:
        for run in runs:
            for buf, pos, size in _documents(src, [run]):
                kind, row = _bson_row(buf, pos, size, run[0] + pos)
                buffers[kind].append(row)
                digests[kind].update(row["raw_bson"])
                counts[kind] += 1
                if len(buffers[kind]) == BATCH_ROWS:
                    flush(kind)
        for kind, rows in buffers.items():
            if rows:
                flush(kind)
    finally:
        for writer in writers.values():
            writer.close()
    result = []
    for kind, path in sorted(paths.items()):
        expected = digests[kind].hexdigest()
        actual = hashlib.sha256()
        for batch in pq.ParquetFile(path).iter_batches(columns=["raw_bson"]):
            for blob in batch.column(0):
                actual.update(blob.as_py())
        if actual.hexdigest() != expected:
            raise ValueError(f"BSON round-trip checksum mismatch in {path}")
        result.append(dict(_verified_file(path, root, counts[kind]), source_type=kind, bson_sha256=expected))
    return result


def convert_lifesnaps(src: Path, out: Path, *, participant_index: int | None = None, workers: int = 4) -> dict:
    if workers < 1 or (participant_index is not None and participant_index < 0):
        raise ValueError("workers must be positive and participant index nonnegative")
    with atomic_directory(out) as root:
        start = time.perf_counter()
        index = index_participants(src)
        if not index:
            raise ValueError("Empty LifeSnaps source")
        jobs = list(enumerate(index.values()))
        if participant_index is not None:
            if participant_index >= len(jobs):
                raise ValueError(f"Participant index must be below {len(jobs)}")
            jobs = [jobs[participant_index]]
        convert = partial(_life_partition, src, root)
        pilot_start = time.perf_counter()
        files = convert(jobs[0])
        pilot = {
            "seconds": round(time.perf_counter() - pilot_start, 2),
            "input_bytes": sum(end - begin for begin, end in jobs[0][1]),
            "parquet_bytes": sum(f["bytes"] for f in files),
            "rows": sum(f["rows"] for f in files),
        }
        print(f"LifeSnaps participant benchmark: {json.dumps(pilot)}", flush=True)
        if len(jobs) > 1:
            if workers == 1:
                for job in jobs[1:]:
                    files.extend(convert(job))
            else:
                with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
                    for result in pool.map(convert, jobs[1:]):
                        files.extend(result)
        counts: Counter[str] = Counter()
        for item in files:
            counts[item["source_type"]] += item["rows"]
        manifest = {
            "source": "lifesnaps",
            "license": "CC BY 4.0",
            "source_bytes": src.stat().st_size,
            "source_sha256": sha256(src),
            "participants": len(jobs),
            "pilot": pilot,
            "seconds": round(time.perf_counter() - start, 2),
            "rows": sum(counts.values()),
            "rows_by_type": dict(counts),
            "files": files,
        }
        write_manifest(root, manifest)
    return manifest


def convert_kaggle(src: Path, out: Path) -> dict:

    def read_csv() -> pacsv.CSVStreamingReader:
        return pacsv.open_csv(
            src,
            read_options=pacsv.ReadOptions(block_size=4 << 20),
            parse_options=pacsv.ParseOptions(newlines_in_values=True),
            convert_options=pacsv.ConvertOptions(column_types={name: pa.string() for name in KAGGLE_COLUMNS}),
        )

    with atomic_directory(out) as root:
        reader = read_csv()
        if tuple(reader.schema.names) != KAGGLE_COLUMNS:
            raise ValueError("Unexpected Kaggle Apple Health CSV columns")
        path = root / "records.parquet"
        rows = 0
        with pq.ParquetWriter(path, reader.schema, compression="zstd") as writer:
            for batch in reader:
                writer.write_batch(batch)
                rows += batch.num_rows
        with pq.ParquetFile(path) as parquet:
            # Each parser batch was written as one row group so values and quoting can
            # be checked against a fresh parse, separately from the file hashes.
            for group, batch in zip(range(parquet.num_row_groups), read_csv(), strict=True):
                if not parquet.read_row_group(group).equals(pa.Table.from_batches([batch])):
                    raise ValueError(f"Kaggle value round-trip mismatch in row group {group}")
        manifest = {
            "source": "kaggle",
            "license": KAGGLE_LICENSE,
            "source_sha256": sha256(src),
            "source_bytes": src.stat().st_size,
            "rows": rows,
            "files": [_verified_file(path, root, rows)],
        }
        write_manifest(root, manifest)
    return manifest
