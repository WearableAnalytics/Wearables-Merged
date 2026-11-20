import os
import tomllib
import warnings
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from zepp_data import write_zepp_csv

from persona_gen import SyntheticRecipe, generate_dataset, load_params, open_dataset
from persona_gen.calibration import zepp
from persona_gen.calibration.zepp import ENV_DISABLE, ensure_zepp_overlay, fit_zepp, fitted_overlays

OWNERSHIP = """
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
"""


class ZeppFitTests(TestCase):
    def setUp(self) -> None:  # a surrounding test session may have switched fitted defaults off
        patch = mock.patch.dict(os.environ, {ENV_DISABLE: "1"})
        patch.start()
        self.addCleanup(patch.stop)

    def test_overlay_recovers_the_structure_of_the_export_and_loads(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = ensure_zepp_overlay(root / "home", write_zepp_csv(root / "kaggle.csv"))
            assert overlay is not None
            text = overlay.read_text(encoding="utf-8")
            model = tomllib.loads(text)["models"]["zepp_amazfit"]
            hr, steps, sleep = model["metrics"]["heart_rate"], model["metrics"]["steps"], model["metrics"]["sleep"]
            self.assertEqual((hr["grid_seconds"], hr["grid_interval_seconds"]), (60.0, 59.0))
            self.assertEqual(hr["grid_burst"]["day_probability"], 0.5)
            self.assertEqual(hr["grid_burst"]["sample_seconds"], 3.0)
            self.assertEqual((steps["grid_seconds"], steps["end_offset_seconds"]), (600.0, -1.0))
            self.assertEqual(model["metrics"]["active_energy"], steps)
            self.assertEqual((sleep["epoch_seconds"], sleep["merge_awake_under_minutes"]), (60.0, 1.0))
            self.assertTrue(sleep["in_bed"])
            self.assertEqual(len(model["delivery"]["write_lag"]["heart_rate"]), 3)
            params = load_params(overlays=[overlay])  # labelled and valid
            self.assertIn("zepp_amazfit", params["devices"]["models"])

    def test_overlay_is_cached_until_the_input_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_zepp_csv(root / "kaggle.csv")
            first = ensure_zepp_overlay(root / "home", source)
            with mock.patch.object(zepp, "convert_kaggle", side_effect=AssertionError("re-fitted")):
                self.assertEqual(ensure_zepp_overlay(root / "home", source), first)
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")  # same rows, new digest
            with mock.patch.object(zepp, "convert_kaggle", wraps=zepp.convert_kaggle) as convert:
                ensure_zepp_overlay(root / "home", source)
            convert.assert_called_once()

    def test_without_the_dataset_a_cached_overlay_is_used_and_otherwise_none(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "absent.csv"
            self.assertIsNone(ensure_zepp_overlay(root / "home", missing))
            with self.assertWarnsRegex(UserWarning, "Zepp"):
                self.assertEqual(fitted_overlays(home=root / "home", kaggle_csv=missing), ())
            cached = ensure_zepp_overlay(root / "home", write_zepp_csv(root / "kaggle.csv"))
            self.assertEqual(ensure_zepp_overlay(root / "home", missing), cached)
            with mock.patch.dict(os.environ, {ENV_DISABLE: "0"}), warnings.catch_warnings():
                warnings.simplefilter("error")
                self.assertEqual(fitted_overlays(home=root / "home", kaggle_csv=missing), ())

    def test_too_little_data_is_refused(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = ensure_zepp_overlay(root / "home", write_zepp_csv(root / "kaggle.csv"))
            assert overlay is not None
            with self.assertRaisesRegex(ValueError, "Too few"):
                fit_zepp(root / "home/calibration/generated/zepp/adapted", before="2024-06-02")

    def test_generate_builds_the_overlay_and_uses_it(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_zepp_csv(root / "kaggle.csv")
            ownership = root / "ownership.toml"
            ownership.write_text(OWNERSHIP)
            manifest = generate_dataset(
                root / "fixture",
                SyntheticRecipe(date(2026, 1, 1), 8, 4, 42),
                overlays=[ownership],
                fitted_defaults=True,
                home=root / "home",
                kaggle_csv=source,
            )
            dataset = open_dataset(manifest)
            values = dataset.manifest["params"]["values"]
            self.assertIn("data", values["overlay:ownership.toml"])
            self.assertIn("data", values["overlay:devices-zepp-amazfit.toml"])
            self.assertTrue((root / "home/calibration/generated/devices-zepp-amazfit.toml").is_file())
            self.assertIn("Amazfit", dataset.table("observations").column("device_model").unique().to_pylist())
