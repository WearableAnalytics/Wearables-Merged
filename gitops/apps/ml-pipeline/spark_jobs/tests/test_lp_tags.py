"""Checks jobs/lp_tags.py against line protocol as the mapper and importservice produce it.

Runs inside the Spark job image, no Kafka or S3 needed:

  docker run --rm -v "$PWD":/opt/spark/work-dir wearables-local/streaming-ml-pipeline:latest \
    /opt/spark/bin/spark-submit --master 'local[1]' /opt/spark/work-dir/tests/test_lp_tags.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jobs"))

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql.functions import col  # noqa: E402

from lp_tags import patient_id  # noqa: E402

P = "11111111-1111-4111-8111-111111111111"

CASES = [
    # Mapper output (ReliableProcessorTest), as published to wearables-lp: tags sorted, provenance appended.
    ("current",
     f'heart-rate,category=measurements.instantaneous,device-id-reference=Patient/{P},ingestion-source=app,'
     f'patient-id={P},source-device-id=phone-installation-9,version=1.0.0 '
     f'value=72.12345678901234,ingestion_record_id="r1",ingestion_mapper_version="m1" 1793355300000000000',
     P),
    # patient-id wins even when the reference disagrees.
    ("explicit tag first",
     'heart-rate,device-id-reference=Patient/other,patient-id=abc value=1 1', "abc"),
    # source-device-id must not be mistaken for a patient tag; escaped characters are unescaped.
    ("escaped values",
     r'heart-rate,patient-id=a\ b\,c\=d,source-device-id=phone\ one\,part\=2 value=1 1', "a b,c=d"),
    # Before the patient-id tag: only the FHIR reference.
    ("legacy reference",
     f'heart-rate,device-id-reference=Patient/{P},source-device-id=phone value=1 1', P),
    # main before reliable-ingestion: device-id and device-id-reference both held the patient.
    ("legacy main",
     f'heart-rate,device-id={P},device-id-reference=Patient/{P},category=x value=1 1', P),
    # A field (after the first unescaped space) named like the tag is ignored.
    ("field is not a tag",
     'heart-rate,source-device-id=phone value=1,patient-id="x" 1', None),
    ("no patient", "heart-rate,source-device-id=phone value=1 1", None),
    ("empty tag", "heart-rate,patient-id=,source-device-id=phone value=1 1", None),
    ("reference without prefix", "heart-rate,device-id-reference=Device/x value=1 1", None),
]


def main() -> None:
    spark = SparkSession.builder.master("local[1]").appName("test_lp_tags").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    df = spark.createDataFrame([(name, payload) for name, payload, _ in CASES], "name string, raw_payload string")
    got = {r["name"]: r["patient_id"] for r in df.select("name", patient_id(col("raw_payload")).alias("patient_id")).collect()}

    failures = [f"{name}: expected {want!r}, got {got[name]!r}" for name, _, want in CASES if got[name] != want]
    spark.stop()
    if failures:
        print("FAILED\n  " + "\n  ".join(failures))
        sys.exit(1)
    print(f"OK: {len(CASES)} cases")


if __name__ == "__main__":
    main()
