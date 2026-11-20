from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
import pyarrow.compute as pc

from persona_gen import SyntheticRecipe, generate_dataset, load_params, open_dataset
from persona_gen.calibration import fit_lognormal_mixture
from persona_gen.persona.sampler import assign_roster, cohort_of
from persona_gen.persona.synthea import SyntheaPatient, synthea_command
from persona_gen.physiology.ecg import classify, waveform
from persona_gen.validation import behaviour_report, structure_report
from persona_gen.validation.checks import _col

ANCHORS = Path(__file__).with_name("fixtures") / "anchors.toml"  # Garmin + Apple Watch test anchors


def _overlay(root: Path, name: str, target: str, body: str) -> Path:
    path = root / f"{name}.toml"
    path.write_text(f'[meta]\ntarget = "{target}"\nversion = "test"\n\n{body}', encoding="utf-8")
    return path


class ScheduleTests(TestCase):
    def test_night_shifts_sleep_in_the_morning_and_naps_reach_nap_detecting_devices(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = ",\n".join(["  [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]"] * 6)
            occupations = _overlay(
                root, "pop", "population", f'[occupations]\nsource = "assumption: test"\nweights = [\n{rows}\n]\n'
            )
            devices = _overlay(
                root,
                "dev",
                "devices",
                (
                    "[ownership]\nwearable_by_age = [[18, 1.0], [90, 1.0]]\nios_share = "
                    "1.0\nabandonment_rate_per_year = 0.0\n"
                    "ios_wearables = { garmin = 1.0 }\n"
                    "archetype_multiplier = "
                    "{ sedentary = 1.0, weekend_warrior = 1.0, "
                    "regular_exerciser = 1.0, athlete = 1.0, older_daily_walker = 1.0 }\n"
                    "[wear]\nadherence_beta = [50.0, 1.0]\nnight_wear_beta = [50.0, 1.0]\nshort_removal_per_day = 0.0\n"
                ),
            )
            overlays = [occupations, devices]
            ds = open_dataset(
                generate_dataset(root / "ds", SyntheticRecipe(date(2026, 3, 2), 21, 6, 3), overlays=overlays)
            )
            params = load_params(overlays=overlays)
            for check in structure_report(ds) + behaviour_report(ds, params):
                self.assertTrue(check["passed"], check)
            nights = ds.table("truth_nights").to_pylist()
            morning = [n for n in nights if not n["nap"] and 4 <= n["onset"].hour <= 9]  # UTC; Berlin-ish zones mostly
            self.assertGreater(len(morning), 3)
            naps = {n["seq"] for n in nights if n["nap"]}
            self.assertTrue(naps)
            sleep = ds.table("observations", filter=pc.field("metric") == "sleep")
            refs = set(zip(_col(sleep, "patient_id"), _col(sleep, "truth_seq"), strict=True))
            nap_keys = {(n["patient_id"], n["seq"]) for n in nights if n["nap"] and n["asleep_seconds"] >= 1200}
            self.assertTrue(refs & nap_keys)


class ExtraTypeTests(TestCase):
    def test_ecg_routes_and_rare_logging_types(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohorts = _overlay(
                root,
                "cohorts",
                "cohorts",
                (
                    '[anchors.profiles.watch_athlete]\ntimezone = "Europe/Berlin"\nlatitude = 52.5\nlongitude = 13.4\n'
                    "[anchors.profiles.watch_athlete.traits]\necg_per_week = 3.0\nafib_history = 1.0\nadherence = "
                    "0.99\nnight_wear = 0.99\n"
                ),
            )
            habits = _overlay(
                root,
                "pop",
                "population",
                ("[habits]\nalcohol_logger_share = 1.0\nheight_logger_share = 1.0\nnutrition_logger_share = 1.0\n"),
            )
            ds = open_dataset(
                generate_dataset(
                    root / "ds",
                    SyntheticRecipe(date(2026, 6, 1), 21, 3, 9, twins=True),
                    overlays=[ANCHORS, cohorts, habits],
                )
            )
            metrics = set(_col(ds.table("observations", columns=["metric"]), "metric"))
            for metric in (
                "alcoholic_beverages",
                "height",
                "dietary_iron",
                "afib_burden",
                "walking_steadiness",
                "six_minute_walk_distance",
                "stair_ascent_speed",
                "estimated_workout_effort",
            ):
                self.assertIn(metric, metrics)
            ecg = ds.table("ecg").to_pylist()
            self.assertTrue(ecg)
            self.assertEqual(len(ecg[0]["voltage_uv"]), 512 * 30)
            routes = ds.table("routes", filter=pc.field("patient_id") == "synthetic-9-0000001")
            self.assertGreater(routes.num_rows, 100)
            self.assertTrue(np.all(np.abs(_col(routes, "latitude") - 52.5) < 2))
            workouts = ds.table("workouts")
            keys = set(zip(_col(workouts, "device_id"), _col(workouts, "truth_workout"), strict=True))
            for key in set(zip(_col(routes, "device_id"), _col(routes, "truth_workout"), strict=True)):
                self.assertIn(key, keys)

    def test_ecg_waveform_classes(self) -> None:
        rng = np.random.default_rng(3)
        normal = waveform(65.0, seconds=30, hz=512, afib=False, quality=0.95, rng=rng)
        self.assertEqual(normal.size, 15360)
        self.assertGreater(float(normal.max()), 700)
        self.assertEqual(classify(65, False, 0.9), "sinus_rhythm")
        self.assertEqual(classify(70, True, 0.9), "atrial_fibrillation")
        self.assertEqual(classify(140, False, 0.9), "inconclusive_high_heart_rate")


class SyntheaTests(TestCase):
    def test_synthea_uses_custom_modules_only_when_requested(self) -> None:
        reference = date(2026, 1, 1)
        command = synthea_command(Path("synthea.jar"), Path("out"), population=10, seed=1, reference=reference)
        self.assertIn("--exporter.csv.export", command)
        self.assertNotIn("-d", command)
        with_modules = synthea_command(
            Path("synthea.jar"), Path("out"), population=10, seed=1, reference=reference, modules=Path("extra-modules")
        )
        self.assertEqual(with_modules[with_modules.index("-d") + 1], "extra-modules")

    def test_roster_assignment_keeps_cohort_shares_and_is_shard_independent(self) -> None:
        from persona_gen.persona.synthea import Entry

        params = load_params()
        roster = [
            SyntheaPatient(
                f"p{i}",
                date(1960 + i % 40, 1, 1),
                None,
                "F" if i % 2 else "M",
                (Entry("Essential hypertension (disorder)", "59621000", date(2010, 1, 1), None),) if i % 3 else (),
                (),
                (),
            )
            for i in range(200)
        ]
        order = np.random.default_rng(0).permutation(len(roster))
        window = (date(2026, 1, 1), date(2026, 2, 1))
        full = assign_roster(params, 5, False, window, roster, order, range(0, 60))
        part = assign_roster(params, 5, False, window, roster, order, range(30, 60))
        self.assertEqual({k: v for k, v in full.items() if k >= 30}, part)
        general = [v[0] for k, v in full.items() if cohort_of(k, params, 5, False)[0] == "general"]
        self.assertEqual(len(general), len(set(general)))


class FitTests(TestCase):
    def test_mixture_fit_recovers_two_modes(self) -> None:
        rng = np.random.default_rng(1)
        gaps = np.concatenate([rng.lognormal(np.log(5), 0.3, 4000), rng.lognormal(np.log(220), 0.5, 6000)])
        fit = sorted(fit_lognormal_mixture(gaps), key=lambda c: c[1])
        self.assertAlmostEqual(fit[0][1], 5, delta=1)
        self.assertAlmostEqual(fit[1][1], 220, delta=30)
        self.assertAlmostEqual(fit[1][0], 0.6, delta=0.05)
