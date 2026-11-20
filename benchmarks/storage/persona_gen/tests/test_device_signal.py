from unittest import TestCase

import numpy as np

from persona_gen import load_params
from persona_gen.devices.ownership import resolve_model


class DeviceSignalTest(TestCase):
    def test_overrides_merge_along_extends_chain(self) -> None:
        models = {
            "a": {"signal": {"hrv_error_sigma": 0.3, "hrv_bias": -0.1}},
            "b": {"extends": "a", "signal": {"hrv_error_sigma": 0.2}},
        }
        merged = resolve_model(models, "b")
        self.assertEqual(merged["signal"], {"hrv_error_sigma": 0.2, "hrv_bias": -0.1})

    def test_shipped_signal_overrides_use_known_keys(self) -> None:
        params = load_params()
        defaults = params["devices"]["signal"]
        for name, spec in params["devices"]["models"].items():
            for key in spec.get("signal", {}):
                if key != "source":
                    self.assertIn(key, defaults, f"{name}: unknown signal key {key}")

    def test_apple_watch_is_tighter_than_defaults(self) -> None:
        params = load_params()
        defaults = params["devices"]["signal"]
        apple = params["devices"]["models"]["apple_watch"]["signal"]
        self.assertLess(apple["noise_multiplier"], defaults["noise_multiplier"])
        self.assertLess(apple["cadence_lock_probability"], defaults["cadence_lock_probability"])
        self.assertLess(apple["hrv_bias"], 0.0)  # Apple SDNN reads low against a chest strap

    def test_sleep_confusion_rows_are_distributions(self) -> None:
        params = load_params()
        for name, spec in params["devices"]["models"].items():
            for row in spec.get("sleep_confusion", {}).get("matrix", []):
                self.assertAlmostEqual(float(np.sum(row)), 1.0, places=6, msg=name)
