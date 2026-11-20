"""Write per-shard Parquet files directly from columnar persona output.

Layout: ``<table>/shard=<n>/[month=YYYY-MM/]part-0.parquet``. Large tables are split by
UTC month of ``start`` so files stay big enough to scan efficiently (a day partition
would create tens of thousands of tiny files). Rows are ordered by persona, then time.
"""

import hashlib
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from ..model import Coded
from .schema import LARGE_TABLES, SCHEMAS

ROW_GROUP = 131_072


def _array(values: Any, field: pa.Field, mask: np.ndarray | None = None) -> pa.Array:
    t = field.type
    if isinstance(values, Coded):
        dictionary = pa.array([str(v) for v in values.values], type=pa.string())
        codes = pa.array(values.codes, type=pa.int32(), mask=values.codes < 0)
        array = pa.DictionaryArray.from_arrays(codes, dictionary)
        return array if pa.types.is_dictionary(t) else array.cast(t)
    if isinstance(values, np.ndarray) and values.dtype.kind == "S":
        array = pa.array(values, type=pa.binary(), mask=mask).cast(pa.string())
        return array
    if pa.types.is_timestamp(t):
        arr = np.asarray(values, dtype=np.float64)
        unit = 1 if t.unit == "s" else 1000
        mask = ~np.isfinite(arr)
        ints = np.where(mask, 0, np.floor(arr * unit)).astype(np.int64)
        return pa.array(ints, type=pa.int64(), mask=mask).cast(t)
    if pa.types.is_date32(t):
        return pa.array([v if isinstance(v, date) else date.fromisoformat(str(v)) for v in values], type=t)
    if pa.types.is_dictionary(t):
        return (
            pa.array(np.asarray(values, dtype=object) if isinstance(values, np.ndarray) else values, type=pa.string())
            .dictionary_encode()
            .cast(t)
        )
    if isinstance(values, np.ndarray) and values.dtype.kind in "fiub":
        if pa.types.is_floating(t) and values.dtype.kind == "f":
            mask = np.isnan(values)
            return pa.array(values, mask=mask if mask.any() else None).cast(t)
        return pa.array(values).cast(t)
    if isinstance(values, np.ndarray):
        values = values.tolist()
    if pa.types.is_floating(t):
        values = [None if v is None or (isinstance(v, float) and np.isnan(v)) else v for v in values]
    return pa.array(values, type=t)


def to_table(name: str, columns: Mapping[str, Any]) -> pa.Table:
    """Build an Arrow table for ``name`` from column arrays using the registered schema. Missing columns become
    nulls.
    """
    schema = SCHEMAS[name]
    arrays = []
    first = next(iter(columns.values()))
    n = len(first)
    mask_for = {"duplicate_of": columns.get("duplicate_mask")}
    for field in schema:
        if field.name in columns:
            mask = mask_for.get(field.name)
            arrays.append(_array(columns[field.name], field, None if mask is None else ~mask))
        else:
            arrays.append(pa.nulls(n, type=field.type))
    return pa.Table.from_arrays(arrays, schema=schema)


class ShardWriter:
    def __init__(self, root: Path, shard: int) -> None:
        self.root = root
        self.shard = shard
        self.writers: dict[tuple[str, str | None], pq.ParquetWriter] = {}
        self.rows: dict[str, int] = {}
        self.pending: dict[tuple[str, str | None], list[pa.Table]] = {}
        self.pending_rows: dict[tuple[str, str | None], int] = {}

    def _path(self, table: str, month: str | None) -> Path:
        path = self.root / table / f"shard={self.shard:05d}"
        if month is not None:
            path = path / f"month={month}"
        path.mkdir(parents=True, exist_ok=True)
        return path / "part-0.parquet"

    def add(self, name: str, columns: Mapping[str, Any]) -> None:
        if not columns or not len(next(iter(columns.values()))):
            return
        table = to_table(name, columns)
        self.rows[name] = self.rows.get(name, 0) + table.num_rows
        if name in LARGE_TABLES:
            keys = _month_keys(
                np.asarray(columns["start"] if "start" in columns else columns["time"], dtype=np.float64)
            )
            for key in np.unique(keys):
                self._buffer(name, _key_to_month(int(key)), table.filter(pa.array(keys == key)))
        else:
            self._buffer(name, None, table)

    def _buffer(self, name: str, month: str | None, table: pa.Table) -> None:
        key = (name, month)
        self.pending.setdefault(key, []).append(table)
        self.pending_rows[key] = self.pending_rows.get(key, 0) + table.num_rows
        if self.pending_rows[key] >= ROW_GROUP:
            self._flush(key)

    def _flush(self, key: tuple[str, str | None]) -> None:
        tables = self.pending.pop(key, [])
        self.pending_rows.pop(key, None)
        if not tables:
            return
        combined = pa.concat_tables(tables).combine_chunks()
        if key not in self.writers:
            self.writers[key] = pq.ParquetWriter(
                self._path(*key),
                combined.schema,
                compression="zstd",
                compression_level=3,
                use_dictionary=True,
                write_statistics=True,
            )
        self.writers[key].write_table(combined, row_group_size=ROW_GROUP)

    def close(self) -> dict[str, Any]:
        """Flush and close all files; return the shard's row counts and per-file SHA-256."""
        for key in list(self.pending):
            self._flush(key)
        for writer in self.writers.values():
            writer.close()
        files = []
        for table, month in sorted(self.writers, key=lambda k: (k[0], k[1] or "")):
            path = self._path(table, month)
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files.append(
                {
                    "table": table,
                    "path": path.relative_to(self.root).as_posix(),
                    "sha256": digest,
                    "rows": pq.ParquetFile(path).metadata.num_rows,
                }
            )
        return {"shard": self.shard, "rows": dict(sorted(self.rows.items())), "files": files}


def _month_keys(start: np.ndarray) -> np.ndarray:
    days = np.floor(start / 86400).astype("datetime64[D]")
    return days.astype("datetime64[M]").astype(np.int64)


def _key_to_month(key: int) -> str:
    return str(np.datetime64(key, "M"))
