import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from persona_gen import (
    TABLES,
    Dataset,
    SyntheticRecipe,
    estimate_rows,
    generate_dataset,
    load_params,
    open_dataset,
)
from persona_gen.config import ParameterError
from persona_gen.output.schema import SCHEMAS
from persona_gen.physiology.heart import ou
from persona_gen.physiology.hrv import simulate
from persona_gen.validation import behaviour_report, effect_report, structure_report
from persona_gen.validation.checks import _col, _daily_observed

ANCHORS = Path(__file__).with_name("fixtures") / "anchors.toml"  # Garmin + Apple Watch test anchors


def _normalized(table: pa.Table) -> pa.Table:
    table = table.drop_columns([c for c in ("shard", "month") if c in table.column_names])
    table = pa.table(
        {
            name: pc.cast(column, pa.string()) if pa.types.is_dictionary(column.type) else column
            for name, column in zip(table.column_names, table.columns, strict=True)
        }
    )
    keys = [k for k in ("patient_id", "seq", "start", "record_id", "time", "device_id") if k in table.column_names]
    return table.sort_by([(k, "ascending") for k in keys]) if table.num_rows else table


def _overlay(root: Path, name: str, target: str, body: str) -> Path:
    path = root / f"{name}.toml"
    path.write_text(f'[meta]\ntarget = "{target}"\nversion = "test"\n\n{body}', encoding="utf-8")
    return path


class ParameterTests(TestCase):
    def test_every_value_has_a_source(self) -> None:
        params = load_params()
        self.assertEqual(
            {name for name in params.versions if ":" not in name},
            {
                "population",
                "behavior",
                "physiology",
                "clinical",
                "cohorts",
                "devices",
                "platforms",
                "delivery",
                "references",
            },
        )
        with TemporaryDirectory() as tmp:
            bad = _overlay(Path(tmp), "bad", "behavior", "[unlabelled]\nvalue = 1\n")
            with self.assertRaises(ParameterError):
                load_params(overlays=[bad])

    def test_overlay_changes_digest(self) -> None:
        with TemporaryDirectory() as tmp:
            overlay = _overlay(Path(tmp), "o", "behavior", "[events.illness]\nrate_per_year = 0.0\n")
            self.assertNotEqual(load_params().digest, load_params(overlays=[overlay]).digest)
            self.assertEqual(load_params(overlays=[overlay])["behavior"]["events"]["illness"]["rate_per_year"], 0.0)


class DeterminismTests(TestCase):
    def test_persona_identical_alone_in_shard_and_full_run(self) -> None:
        recipe = SyntheticRecipe(date(2026, 3, 27), 4, 4, 9, twins=True)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            full = open_dataset(generate_dataset(root / "full", recipe, personas_per_shard=4))
            sharded = open_dataset(generate_dataset(root / "sharded", recipe, personas_per_shard=2))
            alone = open_dataset(
                generate_dataset(
                    root / "alone", SyntheticRecipe(date(2026, 3, 27), 4, 1, 9, first_persona=3, twins=True)
                )
            )
            self.assertEqual(len(full.manifest["shards"]), 1)
            self.assertEqual(len(sharded.manifest["shards"]), 2)
            for table in TABLES:
                a, b = _normalized(full.table(table)), _normalized(sharded.table(table))
                self.assertTrue(a.equals(b), table)
                if a.num_rows and "patient_id" in a.column_names:
                    subset = a.filter(pc.field("patient_id") == "synthetic-9-0000003")
                    c = _normalized(alone.table(table))
                    if subset.num_rows or c.num_rows:
                        self.assertTrue(subset.equals(c), table)
            full.verify()


class DatasetTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        cls.params = load_params(overlays=[ANCHORS])
        cls.manifest = generate_dataset(
            Path(cls.tmp.name) / "ds", SyntheticRecipe(date(2026, 9, 1), 10, 14, 3, twins=True), overlays=[ANCHORS]
        )
        cls.ds = open_dataset(cls.manifest)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_structure_and_traceability(self) -> None:
        for check in structure_report(self.ds):
            self.assertTrue(check["passed"], check)

    def test_behaviour_is_plausible(self) -> None:
        for check in behaviour_report(self.ds, self.params):
            self.assertTrue(check["passed"], check)

    def test_manifest_records_parameters_and_volume(self) -> None:
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(manifest["params"]["sha256"], self.params.digest)
        self.assertGreater(manifest["tables"]["observations"], 1000)
        self.assertTrue(manifest["observation_rows_per_persona_year"])
        self.assertGreater(manifest["run"]["observations_per_second"], 0)

    def test_ids_are_separate_and_stable(self) -> None:
        obs = self.ds.table("observations", columns=["patient_id", "device_id", "wearable_id", "source_name"])
        phone = obs.filter(pc.field("source_name") == "iPhone")
        self.assertEqual(phone["wearable_id"].null_count, phone.num_rows)
        watch = obs.filter(pc.field("source_name") == "Apple Watch")
        if watch.num_rows:
            self.assertEqual(watch["wearable_id"].null_count, 0)

    def test_garmin_writes_on_a_clock_grid_and_apple_watch_does_not(self) -> None:
        obs = self.ds.table(
            "observations",
            columns=["source_name", "metric", "start", "device_id"],
            filter=pc.field("metric") == "heart_rate",
        )
        source = _col(obs, "source_name")
        start = _col(obs, "start")
        device = _col(obs, "device_id")
        for d in np.unique(device[source == "Connect"]):
            gaps = np.diff(np.sort(start[device == d]))
            self.assertTrue(np.all(np.mod(gaps, 120) == 0))
        apple = start[source == "Apple Watch"]
        if apple.size > 200:
            self.assertLess(float((np.mod(apple, 60) == 0).mean()), 0.05)

    def test_truth_and_observations_are_separate(self) -> None:
        derived = self.ds.table("observations", filter=pc.field("metric") == "resting_heart_rate")
        truth = self.ds.table("truth_days")
        self.assertGreater(truth.num_rows, 0)
        if derived.num_rows:
            self.assertTrue(set(_col(derived, "truth_kind")) == {"day"})


class DeliveryTests(TestCase):
    def test_resends_reference_existing_records_and_companion_writes_late(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = _overlay(root, "delivery", "delivery", "[app]\nresend_probability = 0.05\n")
            ds = open_dataset(
                generate_dataset(
                    root / "ds", SyntheticRecipe(date(2026, 2, 1), 5, 4, 12, twins=True), overlays=[ANCHORS, overlay]
                )
            )
            obs = ds.table("observations", columns=["record_id", "duplicate_of", "source_name", "end", "created_at"])
            ids = set(obs["record_id"].to_pylist())
            duplicates = [d for d in obs["duplicate_of"].to_pylist() if d is not None]
            self.assertGreater(len(duplicates), 0)
            self.assertTrue(set(duplicates) <= ids)
            source = _col(obs, "source_name")
            lag = _col(obs, "created_at") - _col(obs, "end")
            # Companion apps (Garmin Connect) write in delayed batches; the native watch near real time.
            self.assertGreater(np.median(lag[source == "Connect"]), 3600)
            self.assertLess(np.median(lag[source == "Apple Watch"]), 600)


class PlatformRuleTests(TestCase):
    def test_series_12_upgrade_densifies_heart_rate_and_rmssd_is_never_written(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = _overlay(
                root,
                "anchors",
                "cohorts",
                (
                    '[anchors.profiles.watch_athlete]\nwearable = "apple_watch"\n'
                    'upgrades = [["2026-09-25", "apple_watch_s12"]]\n'
                    "[anchors.profiles.watch_athlete.traits]\nadherence = 0.99\nnight_wear = 0.99\n"
                ),
            )
            ds = open_dataset(
                generate_dataset(
                    root / "ds", SyntheticRecipe(date(2026, 9, 18), 14, 2, 4, twins=True), overlays=[ANCHORS, overlay]
                )
            )
            obs = ds.table("observations", filter=pc.field("patient_id") == "synthetic-4-0000001")
            metric, start, model = _col(obs, "metric"), _col(obs, "start"), _col(obs, "device_model")
            self.assertNotIn("hrv_rmssd", set(metric))
            upgrade = date(2026, 9, 25)
            hr = metric == "heart_rate"
            before = start[hr & (start < (upgrade - date(1970, 1, 1)).days * 86400)]
            after = start[hr & (model == "Watch8,1")]
            self.assertGreater(after.size, 0)
            per_day_before = before.size / 7
            per_day_after = after.size / max(1, (after.max() - after.min()) / 86400)
            self.assertGreater(per_day_after, 5 * per_day_before)
            events = ds.table("events")
            self.assertIn("hardware_upgrade", set(_col(events, "kind")))

    def test_dst_transition_offsets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = _overlay(
                root,
                "pop",
                "population",
                (
                    '[demographics.timezones]\nsource = "assumption: test"\nnames = ["Europe/Berlin"]\nweights = '
                    "[1.0]\nlatitudes = [52.5]\n"
                ),
            )
            ds = open_dataset(
                generate_dataset(root / "ds", SyntheticRecipe(date(2026, 3, 27), 4, 3, 2), overlays=[overlay])
            )
            offsets = set(_col(ds.table("observations", columns=["start_offset_min"]), "start_offset_min").tolist())
            self.assertEqual(offsets, {60, 120})


class EffectTests(TestCase):
    def test_beta_blocker_start_lowers_observed_resting_hr(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # An independent frozen roster supplies mid-window prescriptions.
            roster = root / "roster"
            roster.mkdir()
            patients = [f"p{i}" for i in range(24)]
            (roster / "patients.csv").write_text(
                "Id,BIRTHDATE,DEATHDATE,GENDER\n" + "".join(f"{p},1968-06-01,,M\n" for p in patients)
            )
            (roster / "medications.csv").write_text(
                "START,STOP,PATIENT,CODE,DESCRIPTION\n"
                + "".join(f"2026-01-26,,{p},866412,Metoprolol Succinate\n" for p in patients)
            )
            devices = _overlay(
                root,
                "devices",
                "devices",
                (
                    "[ownership]\nwearable_by_age = [[18, 1.0], [90, 1.0]]\nabandonment_rate_per_year = 0.0\n"
                    "archetype_multiplier = "
                    "{ sedentary = 1.0, weekend_warrior = 1.0, "
                    "regular_exerciser = 1.0, athlete = 1.0, older_daily_walker = 1.0 }\n"
                    "[wear]\nadherence_beta = [50.0, 1.0]\nnight_wear_beta = [50.0, 1.0]\n"
                ),
            )
            ds = open_dataset(
                generate_dataset(
                    root / "ds", SyntheticRecipe(date(2026, 1, 1), 60, 24, 8), synthea_dir=roster, overlays=[devices]
                )
            )
            report = {c["check"]: c for c in effect_report(ds)}
            check = report["beta_blocker_lowers_resting_hr"]
            self.assertGreater(check["starts"], 2, check)
            self.assertTrue(check["passed"], check)
            truth = ds.table("events")
            self.assertIn("medication_start", set(_col(truth, "kind")))


class SyntheaTests(TestCase):
    def test_roster_drives_conditions_medications_and_events(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roster = root / "synthea"
            roster.mkdir()
            (roster / "patients.csv").write_text("Id,BIRTHDATE,DEATHDATE,GENDER\np1,1960-05-01,,M\np2,1990-01-01,,F\n")
            (roster / "conditions.csv").write_text(
                "START,STOP,PATIENT,ENCOUNTER,CODE,DESCRIPTION\n2015-01-01,,p1,e1,59621000,Essential hypertension "
                "(disorder)\n"
            )
            (roster / "medications.csv").write_text(
                "START,STOP,PATIENT,CODE,DESCRIPTION\n2026-01-10,,p1,866412,24 HR Metoprolol Succinate 100 MG "
                "Extended Release Oral Tablet\n"
            )
            (roster / "encounters.csv").write_text(
                "Id,START,STOP,PATIENT,ENCOUNTERCLASS,CODE,DESCRIPTION\n"
                "e2,2025-12-30,2026-01-03,p1,inpatient,123,Inpatient stay\n"
            )
            # Deliberately request an unavailable matched cohort and a legacy procedure.
            cohorts = _overlay(
                root,
                "cohorts",
                "cohorts",
                '[[cohorts]]\nsource = "spec: general"\nname = "general"\nshare = 0.0\n'
                "age = [18, 90]\nrequire_any = []\n"
                '[[cohorts]]\nsource = "spec: requested"\nname = "cardiac"\nshare = 1.0\n'
                'age = [60, 90]\nrequire_any = ["coronary_heart_disease"]\nprocedure = "surgery"\n',
            )
            ds = open_dataset(
                generate_dataset(
                    root / "ds", SyntheticRecipe(date(2026, 1, 1), 20, 2, 1), synthea_dir=roster, overlays=[cohorts]
                )
            )
            personas = ds.table("personas")
            ids = set(_col(personas, "synthea_id"))
            self.assertEqual(ids, {"p1", "p2"})
            row = next(r for r in personas.to_pylist() if r["synthea_id"] == "p1")
            self.assertEqual(row["age"], 65)
            self.assertEqual(row["cohort"], "general")
            self.assertEqual(row["conditions"], ["hypertension"])
            self.assertIn("beta_blocker", row["medications"])
            events = ds.table("events").to_pylist()
            self.assertTrue(any(e["kind"] == "medication_start" and e["code"] == "beta_blocker" for e in events))
            self.assertEqual([e["code"] for e in events if e["kind"] == "hospitalization"], ["Inpatient stay"])


class WearableOnlyVariantTests(TestCase):
    EVERYDAY = frozenset({"illness", "injury", "mood_episode", "travel"})

    def test_wearable_only_is_plain_by_default_and_events_are_opt_in(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            busy_rates = _overlay(
                root,
                "busy",
                "behavior",
                "[events.illness]\nrate_per_year = 20.0\n\n[events.injury]\nrate_per_year = 20.0\n\n"
                "[events.travel]\nrate_per_year = 20.0\n",
            )
            recipe = SyntheticRecipe(date(2026, 1, 1), 60, 6, 11)
            plain = open_dataset(generate_dataset(root / "plain", recipe, overlays=[busy_rates]))
            events = open_dataset(
                generate_dataset(root / "events", replace(recipe, everyday_events=True), overlays=[busy_rates])
            )
            kinds = {name: set(_col(ds.table("events"), "kind")) for name, ds in (("plain", plain), ("events", events))}
            self.assertFalse(kinds["plain"] & self.EVERYDAY)
            self.assertTrue(kinds["events"] & self.EVERYDAY)
            for ds in (plain, events):
                self.assertEqual(ds.manifest["mode"], "wearable_only")
                self.assertNotIn("everyday_events", ds.manifest["recipe"])
                for persona in ds.table("personas").to_pylist():
                    self.assertEqual((persona["conditions"], persona["medications"]), ([], []))
                for check in structure_report(ds):
                    self.assertTrue(check["passed"], check)
            self.assertIs(plain.manifest["everyday_events"], False)
            self.assertIs(events.manifest["everyday_events"], True)
            same = ("patient_id", "device_id")
            personas = {
                n: ds.table("personas").select(["patient_id"]).to_pylist() for n, ds in (("p", plain), ("e", events))
            }
            self.assertEqual(personas["p"], personas["e"])
            self.assertEqual(
                _normalized(plain.table("devices")).select(
                    [c for c in same if c in plain.table("devices").column_names]
                ),
                _normalized(events.table("devices")).select(
                    [c for c in same if c in events.table("devices").column_names]
                ),
            )

    def test_anchor_runs_keep_everyday_events_and_refuse_plain(self) -> None:
        with TemporaryDirectory() as tmp:
            recipe = SyntheticRecipe(date(2026, 3, 27), 4, 2, 9, twins=True)
            ds = open_dataset(generate_dataset(Path(tmp) / "twins", recipe, overlays=[ANCHORS]))
            self.assertEqual(ds.manifest["mode"], "anchor_comparison")
            self.assertNotIn("everyday_events", ds.manifest)
            with self.assertRaises(ValueError):
                generate_dataset(Path(tmp) / "no", replace(recipe, everyday_events=False), overlays=[ANCHORS])


class ModelTests(TestCase):
    def test_hrv_metrics_come_from_the_same_beats(self) -> None:
        params = load_params()
        windows = simulate(
            np.full(50, 60.0), np.full(50, 40.0), np.full(50, 14.0), 1.2, params, np.random.default_rng(1)
        )
        np.testing.assert_allclose(windows.rmssd, 40.0, rtol=0.05)
        self.assertTrue(np.all(windows.sdnn > 0.9 * windows.rmssd))

    def test_ou_noise_is_exact_at_arbitrary_times(self) -> None:
        rng = np.random.default_rng(2)
        times = np.cumsum(rng.exponential(20.0, 50_000))
        x = ou(times, 45.0, rng)
        self.assertAlmostEqual(float(x.std()), 1.0, delta=0.05)
        expected = 1 / (1 + 20.0 / 45.0)
        self.assertAlmostEqual(float(np.corrcoef(x[:-1], x[1:])[0, 1]), expected, delta=0.03)

    def test_row_estimate(self) -> None:
        estimate = estimate_rows(SyntheticRecipe(date(2026, 1, 1), 365, 10_000, 1), pilot_personas=6, pilot_days=3)
        self.assertGreater(estimate["rows"]["observations"], 10_000 * 365)
        self.assertEqual(estimate["rows"]["personas"], 10_000)
        self.assertEqual(estimate["rows"]["truth_days"], 3_670_000)
        self.assertGreaterEqual(estimate["rows"]["devices"], 10_000)
        self.assertLess(estimate["rows"]["devices"], 30_000)
        self.assertTrue(estimate["observation_rows_per_persona_year"])


class DailyObservationTests(TestCase):
    def test_phone_fallback_and_wearable_filter_use_device_roles(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            ds = Dataset(root, {"shards": [{"shard": 0}]})
            for table, rows in (
                ("devices", [{"device_id": "android", "role": "phone"}, {"device_id": "watch", "role": "wearable"}]),
                (
                    "observations",
                    [
                        {
                            "device_id": device,
                            "patient_id": "p",
                            "metric": "steps",
                            "start": start,
                            "start_offset_min": 0,
                            "value": steps,
                        }
                        for device, start, steps in (
                            ("android", 10, 400.0),
                            ("watch", 10, 700.0),
                            ("android", 86500, 500.0),
                        )
                    ],
                ),
            ):
                shard = root / table / "shard=00000"
                shard.mkdir(parents=True)
                pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[table]), shard / "part.parquet")
            self.assertEqual(_daily_observed(ds, "steps"), {("p", 0): 700.0, ("p", 1): 500.0})
            self.assertEqual(_daily_observed(ds, "steps", wearable_only=True), {("p", 0): 700.0})
