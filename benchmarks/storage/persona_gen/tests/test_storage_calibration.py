import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import pyarrow.parquet as pq
from zepp_data import write_zepp_csv

from persona_gen import SyntheticRecipe, generate_dataset, open_dataset
from persona_gen.calibration.zepp import ensure_zepp_overlay
from persona_gen.sources.observations import adapt_observations
from persona_gen.sources.raw import KAGGLE_COLUMNS, convert_kaggle
from persona_gen.validation.storage import split_people, storage_report


class StorageCalibrationTests(TestCase):
    def test_zepp_fixture_matches_observation_schema_and_reports_date_holdout(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, raw, real = root / "kaggle.csv", root / "raw", root / "real"
            with source.open("w", newline="", encoding="utf-8") as stream:
                csv_writer = csv.writer(stream)
                csv_writer.writerow(KAGGLE_COLUMNS)
                for offset in range(-1, 21):
                    day = (date(2025, 1, 1) + timedelta(days=offset)).isoformat()
                    row = [
                        "StepCount",
                        "Zepp",
                        "1",
                        "count",
                        day,
                        "02:30:00 PM",
                        "PM",
                        "+1100",
                        day,
                        "07:20:00 AM",
                        "AM",
                        "+1100",
                        day,
                        "07:29:59 AM",
                        "AM",
                        "+1100",
                        "101",
                        'device, model "Amazfit"',
                    ]
                    csv_writer.writerow(row)
                    if offset == 0:
                        csv_writer.writerow(row)
            self.assertEqual(convert_kaggle(source, raw)["rows"], 23)
            self.assertEqual(pq.read_table(raw / "records.parquet")["device"][0].as_py(), 'device, model "Amazfit"')
            adapt_observations("kaggle", raw, real)
            sample = pq.read_table(real / "observations/records.parquet").to_pylist()[1]
            self.assertEqual(sample["start"], datetime(2024, 12, 31, 20, 20, tzinfo=UTC))
            self.assertEqual(sample["start_offset_min"], 660)
            self.assertEqual(sample["created_at"].hour, 3)

            overlay = root / "test.toml"
            overlay.write_text("""
[meta]
target = "devices"
replace = ["ownership.ios_wearables"]
[ownership]
ios_share = 1.0
ios_wearables = { zepp_amazfit = 1.0 }
wearable_by_age = [[18, 10.0], [90, 10.0]]
abandonment_rate_per_year = 0.0
[wear]
adherence_beta = [50.0, 1.0]
night_wear_beta = [50.0, 1.0]
""")
            fixture = root / "fixture"
            zepp = ensure_zepp_overlay(root / "home", write_zepp_csv(root / "zepp.csv"))
            assert zepp is not None
            dataset = open_dataset(
                generate_dataset(fixture, SyntheticRecipe(date(2026, 1, 1), 8, 4, 42), overlays=[zepp, overlay])
            )
            self.assertEqual(dataset.manifest["mode"], "wearable_only")
            for persona in dataset.table("personas").to_pylist():
                self.assertEqual(persona["cohort"], "wearable_only")
                self.assertEqual(persona["conditions"], [])
                self.assertEqual(persona["medications"], [])
                self.assertIsNone(persona["anchor"])
                self.assertIsNone(persona["synthea_id"])
            self.assertFalse(
                any(
                    e["kind"] in {"hospitalization", "condition_onset", "mood_episode", "medication_dose"}
                    for e in dataset.table("events").to_pylist()
                )
            )
            report = storage_report(real, [fixture], "zepp_amazfit", repeats=5)
            self.assertEqual(report["real"]["steps"]["rows"], 22)
            self.assertEqual(report["real"]["steps"]["duplicate_rows"], 1)
            self.assertEqual(report["baseline_units"], 3)
            self.assertEqual(report["real_vs_real"]["steps"]["records_p50"]["comparisons"], 5)
            self.assertEqual(report["synthetic"][0]["metrics"]["steps"]["duration_s"], [599.0] * 3)
            self.assertGreater(report["synthetic"][0]["metrics"]["steps"]["lag_s"][1], 3600)

    def test_lifesnaps_holdout_is_disjoint_and_order_independent(self) -> None:
        people = [f"p{i}" for i in range(15)]
        training, held = split_people(people)
        self.assertEqual((training, held), split_people(people[::-1]))
        self.assertEqual(len(held), 5)
        self.assertFalse(set(training) & set(held))
