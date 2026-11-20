"""Device ownership over time: none, phone only, native watch, companion wearable, two
wearables, hardware upgrades (release-gated), platform switches and abandonment."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from ..model import Event
from ..persona.sampler import Persona
from ..timeutil import DAY, utc_seconds
from ..util import choice, interp_table


def resolve_model(models: Mapping[str, Any], name: str) -> dict[str, Any]:
    """Merge a model with the models it extends (metrics merge per metric)."""
    spec = models[name]
    if "extends" not in spec:
        return deepcopy(dict(spec))
    base = resolve_model(models, spec["extends"])
    for key, value in spec.items():
        if key == "extends":
            continue
        if key == "signal":
            base["signal"] = {**base.get("signal", {}), **value}
        elif key == "metrics":
            base["metrics"] = {**base.get("metrics", {}), **{k: v for k, v in value.items() if k != "source"}}
        else:
            base[key] = deepcopy(value)
    base["name"] = name
    return base


@dataclass(slots=True)
class DevicePeriod:
    device_id: str
    wearable_id: str | None
    model: str
    spec: dict[str, Any]
    start: float
    end: float
    role: str  # "wearable" | "phone"
    platform: str
    reason: str
    motion: bool = True  # phone motion permission

    @property
    def archetype(self) -> str:
        return str(self.spec["archetype"])

    def row(self, patient_id: str) -> dict[str, Any]:
        return {
            "patient_id": patient_id,
            "device_id": self.device_id,
            "wearable_id": self.wearable_id,
            "model": self.model,
            "hardware": self.spec["hardware"],
            "source_name": self.spec["source_name"],
            "kind": self.spec["kind"],
            "archetype": self.archetype,
            "platform": self.platform,
            "role": self.role,
            "start": self.start,
            "end": self.end,
            "reason": self.reason,
            "motion_enabled": self.motion,
        }


def _uuid(rng: np.random.Generator) -> str:
    h = rng.bytes(16).hex()
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-{h[16:20]}-{h[20:32]}".upper()


def plan_devices(
    persona: Persona, window: tuple[float, float], params: Mapping[str, Any], rng: np.random.Generator
) -> tuple[list[DevicePeriod], list[Event]]:
    spec = params["devices"]["ownership"]
    models = params["devices"]["models"]
    start, end = window
    years = (end - start) / (365.25 * DAY)
    events: list[Event] = []
    anchor = params["cohorts"]["anchors"]["profiles"][persona.anchor] if persona.anchor else None

    ios = rng.random() < spec["ios_share"]
    wearable_model: str | None = None
    if anchor is not None:
        wearable_model = anchor.get("wearable")
        ios = models[anchor.get("phone", "iphone")]["platform"] == "healthkit"
    else:
        p_own = interp_table(spec["wearable_by_age"], persona.age) * spec["archetype_multiplier"][persona.archetype]
        if rng.random() < min(0.95, p_own):
            wearable_model = choice(rng, spec["ios_wearables"] if ios else spec["android_wearables"])
    phone_model = "iphone" if ios else "android_phone"
    periods: list[DevicePeriod] = []
    lead = rng.uniform(30, 900) * DAY  # devices usually owned before the window
    switch_at = end
    if anchor is None and rng.random() < 1 - np.exp(-spec["platform_switch_rate_per_year"] * years):
        switch_at = start + rng.uniform(0.1, 0.9) * (end - start)
    phone_spec = resolve_model(models, phone_model)
    motion = anchor is not None or rng.random() >= spec["phone_motion_disabled_probability"]
    periods.append(
        DevicePeriod(
            _uuid(rng),
            None,
            phone_model,
            phone_spec,
            start - lead,
            switch_at,
            "phone",
            phone_spec["platform"],
            "initial",
            motion,
        )
    )
    if switch_at < end:
        other = "android_phone" if ios else "iphone"
        other_spec = resolve_model(models, other)
        periods.append(
            DevicePeriod(
                _uuid(rng),
                None,
                other,
                other_spec,
                switch_at,
                end,
                "phone",
                other_spec["platform"],
                "platform_switch",
                motion,
            )
        )
        events.append(Event("platform_switch", switch_at, None, other, {"from": phone_model}))

    acquire_at: float | None = None
    if wearable_model is None and anchor is None and rng.random() < 1 - np.exp(-spec["acquire_rate_per_year"] * years):
        acquire_at = start + rng.uniform(0.05, 0.9) * (end - start)
        wearable_model = choice(rng, spec["ios_wearables"] if ios else spec["android_wearables"])
    if wearable_model is not None:
        wearable_id = _uuid(rng)
        w_start = acquire_at if acquire_at is not None else start - rng.uniform(30, 1200) * DAY
        model_spec = resolve_model(models, wearable_model)
        w_start = max(w_start, utc_seconds(date.fromisoformat(model_spec["available_from"])))
        w_end = end
        if (
            model_spec["platform"] == "healthkit"
            and switch_at < end
            and model_spec["kind"] == "watch"
            and wearable_model.startswith("apple")
        ):
            w_end = switch_at  # Apple Watch cannot pair with Android
        rate = spec["abandonment_rate_per_year"] * persona.abandonment_multiplier
        if anchor is None and rng.random() < 1 - np.exp(-rate * years):
            abandon = start + rng.uniform(0.05, 0.95) * (end - start)
            if abandon < w_end:
                w_end = abandon
                events.append(Event("wearable_abandoned", abandon, None, wearable_model, {}))
        if acquire_at is not None:
            events.append(Event("wearable_acquired", acquire_at, None, wearable_model, {}))
        # Hardware upgrades: release-gated (e.g. Apple Watch Series 12 from its release date).
        upgrades: list[tuple[float, str]] = []
        overlay = (anchor or {}).get("upgrades", [])
        for when, model in overlay:
            upgrades.append((utc_seconds(date.fromisoformat(when)), model))
        if anchor is None and rng.random() < 1 - np.exp(-spec["upgrade_rate_per_year"] * years):
            target = wearable_model
            if wearable_model.startswith("apple_watch"):
                newest = max(
                    (n for n in models if n.startswith("apple_watch")),
                    key=lambda n: resolve_model(models, n)["available_from"],
                )
                target = newest
            release = utc_seconds(date.fromisoformat(resolve_model(models, target)["available_from"]))
            lo = max(start, release, w_start)
            if lo < w_end:
                upgrades.append((lo + rng.exponential(60 * DAY), target))
        cursor, current = w_start, wearable_model
        for when, model in sorted(upgrades):
            if not cursor < when < w_end:
                continue
            spec_now = resolve_model(models, current)
            periods.append(
                DevicePeriod(
                    _uuid(rng),
                    wearable_id,
                    current,
                    spec_now,
                    cursor,
                    when,
                    "wearable",
                    spec_now["platform"],
                    "initial" if cursor == w_start else "upgrade",
                )
            )
            events.append(Event("hardware_upgrade", when, None, model, {"from": current}))
            cursor, current = when, model
        spec_now = resolve_model(models, current)
        periods.append(
            DevicePeriod(
                _uuid(rng),
                wearable_id,
                current,
                spec_now,
                cursor,
                w_end,
                "wearable",
                spec_now["platform"],
                "initial" if cursor == w_start else "upgrade",
            )
        )
        if anchor is None and rng.random() < spec["second_wearable_probability"]:
            second = spec["second_wearable"]["ios" if ios else "android"]
            s_spec = resolve_model(models, second)
            periods.append(
                DevicePeriod(
                    _uuid(rng),
                    _uuid(rng),
                    second,
                    s_spec,
                    max(w_start, start - 200 * DAY),
                    w_end,
                    "wearable",
                    s_spec["platform"],
                    "second",
                )
            )
    return periods, events
