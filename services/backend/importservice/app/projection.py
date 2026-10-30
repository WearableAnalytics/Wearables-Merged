"""Attach provenance without a high-cardinality per-record InfluxDB tag.

Reserve each final series/timestamp for one source record before publishing it.
Different records that collide are rejected, not silently merged by InfluxDB.
"""

import re

from .crypto import canonical, digest


def split_escaped(value, delimiter):
    parts, current, escaped = [], [], False
    for char in value:
        if char == delimiter and not escaped:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        escaped = char == "\\" and not escaped
    parts.append("".join(current))
    return parts


def prepare_projection(line, row, mapper_version):
    if not isinstance(line, str) or len(line.encode()) > 32_000 or any(c in line for c in "\r\n\x00"):
        raise ValueError("Invalid line protocol")
    # Prefix spaces are escaped; the final separator precedes the integer timestamp.
    prefix_end = None
    escaped = False
    for index, char in enumerate(line):
        if char == " " and not escaped:
            prefix_end = index
            break
        escaped = char == "\\" and not escaped
    if prefix_end is None:
        raise ValueError("Invalid line protocol prefix")
    head = line[:prefix_end]
    fields, timestamp = line[prefix_end + 1 :].rsplit(" ", 1)
    if not re.fullmatch(r"-?\d{1,19}", timestamp) or not -(2**63) < int(timestamp) < 2**63:
        raise ValueError("Invalid line protocol timestamp")
    tags = split_escaped(head, ",")
    if any(tag.startswith("ingestion-") for tag in tags[1:]) or "ingestion_" in fields:
        raise ValueError("Reserved lineage field")
    tags.append("ingestion-source=" + row["source_key"])
    # Sort tags because order does not change an InfluxDB series identity.
    prefix = tags[0] + "," + ",".join(sorted(tags[1:]))
    point_key = digest(canonical([prefix, int(timestamp)]))
    output_hash = digest(canonical([line, str(row["id"]), row["input_sha256"], mapper_version, row["source_key"]]))
    references = {
        "ingestion_record_id": str(row["id"]),
        "ingestion_upload_id": str(row["first_upload_id"]),
        "ingestion_raw_sha256": row["raw_sha256"],
        "ingestion_mapper_version": mapper_version,
        "ingestion_input_sha256": row["input_sha256"],
        "ingestion_output_sha256": output_hash,
    }
    extra = ",".join(f'{name}="{value}"' for name, value in references.items())
    return point_key, output_hash, f"{prefix} {fields},{extra} {timestamp}".encode(), int(timestamp)
