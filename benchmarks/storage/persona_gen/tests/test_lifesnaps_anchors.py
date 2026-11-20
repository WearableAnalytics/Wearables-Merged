import struct
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

import numpy as np
import pyarrow.parquet as pq

from persona_gen import SyntheticRecipe, generate_dataset, load_params, open_dataset
from persona_gen.sources.lifesnaps_bson import (
    anchor_traits,
    anchors_overlay,
    device_overlay,
    index_participants,
    profile_participant,
    select_anchors,
)
from persona_gen.sources.observations import adapt_observations
from persona_gen.sources.raw import convert_lifesnaps, sha256
from persona_gen.validation.checks import _col


def _overlay(root: Path, name: str, target: str, body: str, replace: str = "") -> Path:
    path = root / f"{name}.toml"
    meta = f'[meta]\ntarget = "{target}"\nversion = "test"\n{replace}\n'
    path.write_text(meta + body, encoding="utf-8")
    return path


def _element(key: str, value: Any) -> bytes:
    name = key.encode() + b"\0"
    if isinstance(value, bool):
        return b"\x08" + name + bytes([value])
    if isinstance(value, int):
        return b"\x10" + name + struct.pack("<i", value)
    if isinstance(value, float):
        return b"\x01" + name + struct.pack("<d", value)
    if isinstance(value, bytes):
        return b"\x07" + name + value
    if isinstance(value, str):
        raw = value.encode() + b"\0"
        return b"\x02" + name + struct.pack("<i", len(raw)) + raw
    if isinstance(value, list):
        return b"\x04" + name + _bson({str(i): v for i, v in enumerate(value)})
    return b"\x03" + name + _bson(value)


def _bson(doc: dict[str, Any]) -> bytes:
    body = b"".join(_element(k, v) for k, v in doc.items()) + b"\0"
    return struct.pack("<i", len(body) + 4) + body


def _doc(uid: bytes, kind: str, data: dict[str, Any]) -> bytes:
    return _bson({"_id": bytes(12), "id": uid, "type": kind, "data": data})


def _participant(uid: bytes, start: datetime, days: int) -> list[bytes]:
    docs = [_doc(uid, "Profile", {"gender": "FEMALE", "age": ">=30", "bmi": "22.0"})]
    for d in range(days):
        night = start + timedelta(days=d, hours=23)
        wake = night + timedelta(hours=8)
        docs.append(
            _doc(
                uid,
                "sleep",
                {
                    "dateOfSleep": wake.date().isoformat(),
                    "startTime": night.isoformat() + ".000",
                    "endTime": wake.isoformat() + ".000",
                    "minutesAsleep": 450,
                    "efficiency": 94,
                    "type": "stages",
                    "mainSleep": True,
                    "levels": {
                        "summary": {
                            k: {"minutes": m} for k, m in (("deep", 80), ("light", 250), ("rem", 90), ("wake", 30))
                        },
                        "data": [{"dateTime": night.isoformat(), "level": "light", "seconds": 1800}],
                    },
                },
            )
        )
        day = start + timedelta(days=d + 1)
        docs.append(
            _doc(uid, "resting_heart_rate", {"dateTime": day.strftime("%m/%d/%y 00:00:00"), "value": {"value": 58.0}})
        )
    t = start
    while t < start + timedelta(days=days):
        hour = t.hour
        asleep = hour == 23 or hour < 7
        docs.append(_doc(uid, "heart_rate", {"dateTime": t.isoformat(), "value": {"bpm": 55 if asleep else 70}}))
        if not asleep and t.second == 0 and t.minute % 2 == 0:
            docs.append(_doc(uid, "steps", {"dateTime": t.isoformat(), "value": "40"}))
        t += timedelta(seconds=10 if asleep else 5)
    return docs


class LifeSnapsBsonTests(TestCase):
    def test_profiles_interleaved_participants_from_bson(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fitbit.bson"
            a = _participant(b"a" * 12, datetime(2021, 5, 24), 3)
            b = _participant(b"b" * 12, datetime(2021, 6, 1), 1)
            path.write_bytes(b"".join(a[:5] + b[:3] + a[5:] + b[3:]))  # runs interleave, as in the dump
            index = index_participants(path, chunk=1 << 16)
            self.assertEqual(set(index), {(b"a" * 12).hex(), (b"b" * 12).hex()})
            self.assertEqual(len(index[(b"a" * 12).hex()]), 2)
            p = profile_participant(path, index[(b"a" * 12).hex()])
            hr = p["heart_rate"]
            self.assertEqual(p["profile"]["gender"], "FEMALE")
            self.assertEqual(hr["worn_days"], 3)
            self.assertEqual(hr["night_wear"], 1.0)
            histogram = hr["gap_histogram"]
            self.assertEqual(max(histogram["sleep"], key=histogram["sleep"].get), "10")
            self.assertEqual(max(histogram["moving"], key=histogram["moving"].get), "5")
            self.assertEqual(p["daily"]["resting_hr"][2], 58.0)
            self.assertEqual(hr["asleep_median"], 55.0)

    def test_raw_conversion_preserves_unknown_document_and_local_intervals(self) -> None:
        uid = b"a" * 12
        steps = _doc(uid, "steps", {"dateTime": "2021-10-31T02:30:00", "value": "12"})
        unknown = _doc(uid, "future/type", {"opaque": ["kept", 3]})
        sleep = _doc(
            uid,
            "sleep",
            {
                "startTime": "2021-10-31T02:00:00",
                "endTime": "2021-10-31T09:00:00",
                "levels": {"data": [{"dateTime": "2021-10-31T02:00:00", "level": "light", "seconds": 60}]},
            },
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fitbit.bson"
            source.write_bytes(steps + unknown + sleep)
            raw, observations = root / "raw", root / "normalized"
            manifest = convert_lifesnaps(source, raw, workers=1)
            self.assertEqual(manifest["source_sha256"], sha256(source))
            self.assertEqual(manifest["rows_by_type"], {"steps": 1, "future/type": 1, "sleep": 1})
            unknown_part = next(item for item in manifest["files"] if item["source_type"] == "future/type")
            raw_row = pq.read_table(raw / unknown_part["path"]).to_pylist()[0]
            self.assertEqual((raw_row["raw_bson"], raw_row["source_offset"]), (unknown, len(steps)))
            adapt_observations("lifesnaps", raw, observations)
            row = pq.read_table(observations / "observations/steps/000.parquet").to_pylist()[0]
            self.assertIsNone(row["start_offset_min"])
            self.assertIsNone(row["created_at"])
            self.assertEqual(row["value"], 12)
            self.assertEqual((row["end"] - row["start"]).total_seconds(), 60)
            stage_rows = pq.read_table(observations / "observations/sleep/000.parquet").to_pylist()
            self.assertEqual([r["category"] for r in stage_rows if r["metric"] == "sleep"], ["asleep_core"])

    def test_anchor_selection_and_overlays(self) -> None:
        rng = np.random.default_rng(1)
        people = []
        for i in range(30):
            steps = float(rng.uniform(3000, 15000))
            people.append(
                {
                    "id": f"p{i:02d}",
                    "profile": {
                        "gender": "FEMALE" if i % 2 else "MALE",
                        "age": "<30" if i < 15 else ">=30",
                        "bmi": "<19",
                    },
                    "heart_rate": {
                        "worn_days": 60,
                        "wear_fraction": 0.9,
                        "night_wear": 0.8,
                        "gap_histogram": {"sleep": {"5": 900, "15": 300}, "still": {"5": 1000}, "moving": {"5": 800}},
                    },
                    "sleep": {"nights": 50, "midsleep_hour": [3, 3.5, 4, 4.5, 5], "asleep_hours": [6, 6.5, 7, 7.5, 8]},
                    "steps": {"daily": [steps * 0.6, steps * 0.8, steps, steps * 1.2, steps * 1.4]},
                    "daily": {"resting_hr": [55, 58, 60 + i % 10, 62, 65], "rmssd": [30, 35, 40, 45, 50]},
                    "exercise": {"per_week": 3.0, "names": {"Walk": 10, "Run": 5}},
                }
            )
        people.append({"id": "short", "profile": {"gender": "MALE"}, "heart_rate": {"worn_days": 5}})
        chosen = select_anchors(people, 4)
        self.assertEqual(len(chosen), 4)
        self.assertNotIn("short", [p["id"] for p in chosen])
        self.assertEqual(select_anchors(people, 4), chosen)  # deterministic
        entry = anchor_traits(people[0])
        self.assertEqual(
            (entry["wearable"], entry["phone"], entry["traits"]["bmi"]), ("fitbit_sense", "android_phone", 18.3)
        )
        overlay = anchors_overlay({"participants": people}, k=4)
        self.assertEqual(overlay["meta"]["replace"], ["anchors.profiles"])
        self.assertEqual(len(overlay["anchors"]["profiles"]), 4)
        cadence = device_overlay({"participants": people})["models"]["fitbit_sense"]["metrics"]["heart_rate"]["cadence"]
        self.assertEqual(set(cadence), {"sleep", "still", "moving"})


class AnchorSetTests(TestCase):
    def test_default_anchors_are_lifesnaps_and_fitbit(self) -> None:
        params = load_params()
        self.assertEqual(params["cohorts"]["anchors"]["share"], 0)
        self.assertGreater(params["devices"]["ownership"]["android_wearables"]["fitbit_sense"], 0)
        profiles = params["cohorts"]["anchors"]["profiles"]
        self.assertTrue(profiles)
        self.assertTrue(all(name.startswith("lifesnaps_") for name in profiles))
        self.assertTrue(all(p["source"].startswith("calibrated: LifeSnaps") for p in profiles.values()))
        self.assertIn("fitbit_sense", params["devices"]["models"])
        self.assertEqual(dict(load_params(defaults=False)["cohorts"]["anchors"]["profiles"]), {})

    def test_replace_swaps_the_anchor_set_in_any_file_order(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            root.mkdir()
            # Traits sort before the descriptors that carry the replace: order must not matter.
            _overlay(root, "a-traits", "cohorts", "[anchors.profiles.me.traits]\nrhr = 51.0\n")
            _overlay(
                root,
                "b-descriptors",
                "cohorts",
                '[anchors.profiles.me]\nsource = "spec: test"\nage = 40\nsex = "F"\narchetype = "athlete"\n'
                'wearable = "garmin"\nphone = "iphone"\nconditions = []\nmedications = []\n',
                replace='replace = ["anchors.profiles"]',
            )
            params = load_params(overlays=[root])
            self.assertEqual(list(params["cohorts"]["anchors"]["profiles"]), ["me"])
            self.assertEqual(params["cohorts"]["anchors"]["profiles"]["me"]["traits"]["rhr"], 51.0)
            self.assertNotEqual(params.digest, load_params().digest)

    def test_lifesnaps_twins_wear_a_fitbit_with_dense_heart_rate(self) -> None:
        with TemporaryDirectory() as tmp:
            ds = open_dataset(
                generate_dataset(Path(tmp) / "ds", SyntheticRecipe(date(2026, 4, 6), 3, 2, 5, twins=True))
            )
            personas = ds.table("personas").to_pylist()
            self.assertEqual([p["anchor"] for p in personas], ["lifesnaps_01", "lifesnaps_02"])
            obs = ds.table("observations", columns=["patient_id", "metric", "start", "source_name"])
            hr = (_col(obs, "metric") == "heart_rate") & (_col(obs, "source_name") == "Fitbit")
            first = hr & (_col(obs, "patient_id") == personas[1]["patient_id"])
            gaps = np.diff(np.sort(_col(obs, "start")[first].astype(float)))
            self.assertLess(float(np.median(gaps)), 20.0)  # Fitbit intraday HR, not 10-minute background
