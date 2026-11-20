"""Readers for Apple Health export archives (streamed, no extraction to disk)."""

import re
import tarfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO
from xml.etree import ElementTree

# TODO: Convert exports once to a shared Parquet layout (records, hrv_beats, workouts, routes, ecg, other) and
# read calibration data from it. Every run currently re-parses the whole archive.
FILE_KINDS = {".gpx": "route", ".csv": "ecg"}
HK = "HKQuantityTypeIdentifier"
HKC = "HKCategoryTypeIdentifier"


def parse_date(value: str) -> datetime:
    """Parse an export timestamp to UTC. Raises ``ValueError`` if it has no UTC offset."""
    date = datetime.fromisoformat(value)
    if date.tzinfo is None:
        raise ValueError("Expected an export timestamp with a UTC offset")
    return date.astimezone(UTC)


def export_files(archive: Path) -> Iterator[tuple[str, str, IO[bytes]]]:
    """Stream the files of an Apple Health ``.tar.xz`` export as ``(kind, name, stream)``. The xz stream is read
    once, in order.
    """
    with tarfile.open(archive, "r|xz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = PurePosixPath(member.name)
            match name.name.lower():
                case "export.xml":
                    kind = "health-xml"
                case "export_cda.xml":
                    kind = "cda"
                case _:
                    kind = FILE_KINDS.get(name.suffix.lower(), "metadata")
            stream = tar.extractfile(member)
            assert stream is not None
            with stream:
                yield kind, member.name, stream


def xml_entries(stream: IO[bytes]) -> Iterator[ElementTree.Element]:
    """Stream the children of ``HealthData`` one at a time (header element first) and free each after use."""
    root = None
    depth = 0
    for event, element in ElementTree.iterparse(stream, events=("start", "end")):
        if event == "start":
            if depth == 0:
                root = element
                if root.tag != "HealthData":
                    raise ValueError("Expected an Apple Health export")
                # Preserve the header without buffering its children.
                yield ElementTree.Element(root.tag, root.attrib)
            depth += 1
            continue

        depth -= 1
        if depth == 1:
            yield element
            assert root is not None
            root.remove(element)


def family(source: str, device: str | None = None) -> str:
    """Group sources by device family, using the hardware model when the name is custom."""
    if device:
        if "model:iPhone" in device and "Watch" not in source:
            return "iphone"
        # bevel and stresswatch are xternal apps but blood oxygen is just the apple watch blood oxygen app.
        if "model:Watch" in device and source.lower() not in ("bevel", "blood oxygen", "stresswatch"):
            return "apple_watch"
    lowered = source.lower()
    if "watch" in lowered:
        return "apple_watch"
    if "iphone" in lowered:
        return "iphone"
    if lowered in ("connect", "garmin connect"):
        return "garmin"
    return "app:" + re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
