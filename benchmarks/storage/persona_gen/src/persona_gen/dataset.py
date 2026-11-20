"""Read a generated dataset back (for storage loaders, validation and tests)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.dataset as ds


@dataclass(frozen=True, slots=True)
class Dataset:
    root: Path
    manifest: dict[str, Any]

    def shards(self) -> list[int]:
        return [int(s["shard"]) for s in self.manifest["shards"]]

    def table(
        self, name: str, *, columns: list[str] | None = None, filter: Any = None, shard: int | None = None
    ) -> pa.Table:
        """Read a table (optionally one shard) as an Arrow table, with column projection and an optional pyarrow filter.
        Returns an empty table with the schema if no files exist.
        """
        path = self.root / name
        if shard is not None:
            path = path / f"shard={shard:05d}"
        if not path.exists():
            from .output.schema import SCHEMAS

            schema = SCHEMAS[name]
            return (
                schema.empty_table() if columns is None else pa.schema([schema.field(c) for c in columns]).empty_table()
            )
        dataset = ds.dataset(path, format="parquet", partitioning="hive")
        return dataset.to_table(columns=columns, filter=filter)

    def batches(self, name: str, *, columns: list[str] | None = None, batch_size: int = 65_536):
        path = self.root / name
        if not path.exists():
            return iter(())
        files = sorted(str(p) for p in path.rglob("*.parquet"))
        dataset = ds.dataset(files, format="parquet")
        return dataset.to_batches(columns=columns, batch_size=batch_size)

    def verify(self) -> None:
        for shard in self.manifest["shards"]:
            for item in shard["files"]:
                path = self.root / item["path"]
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                        raise ValueError(f"Checksum mismatch: {item['path']}")


def open_dataset(manifest_or_root: Path) -> Dataset:
    """Open a dataset from its directory or its ``manifest.json``. Raises ``ValueError`` unless it is a version 2
    synthetic manifest.
    """
    path = Path(manifest_or_root)
    root = path.parent if path.name == "manifest.json" else path
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("origin") != "synthetic" or manifest.get("version") != 2:
        raise ValueError("Expected a version 2 synthetic dataset manifest")
    return Dataset(root, manifest)
