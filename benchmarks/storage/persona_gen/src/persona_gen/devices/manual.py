"""Manually logged or third-party data written through the phone (scales, BP cuffs, nutrition)."""

import numpy as np

from ..behavior.timeline import Timeline
from ..persona.sampler import Persona
from ..physiology.daily import DailyState
from ..timeutil import HOUR, MINUTE
from .context import Batch


def manual_batches(
    persona: Persona, timeline: Timeline, daily: DailyState, rng: np.random.Generator, window: tuple[float, float]
) -> list[tuple[str, Batch]]:
    out: list[tuple[str, Batch]] = []
    wake = timeline.wake
    n = len(wake)
    days = np.arange(n)
    if persona.weight_logger:
        p = 0.75 if persona.weight_logger == "scale" else 0.12
        chosen = days[rng.random(n) < p]
        t = wake[chosen] + rng.uniform(2, 25, len(chosen)) * MINUTE
        drift = np.cumsum(rng.normal(0, 0.0015, n))
        weight = persona.weight_kg * (1 + drift[chosen]) + rng.normal(0, 0.35, len(chosen))
        source = "Withings" if persona.weight_logger == "scale" else "Health"
        out.append(
            (source, Batch("body_mass", t, t.copy(), np.round(weight, 2), None, "day", chosen, lag_class="manual"))
        )
        bmi = weight / (persona.height_cm / 100) ** 2
        out.append(
            (source, Batch("body_mass_index", t, t.copy(), np.round(bmi, 2), None, "day", chosen, lag_class="manual"))
        )
        if persona.weight_logger == "scale":
            fat = np.clip(
                0.12
                + 0.012 * (persona.bmi - 22)
                + (0.08 if persona.sex == "F" else 0)
                + rng.normal(0, 0.01, len(chosen)),
                0.04,
                0.5,
            )
            out.append(
                (
                    source,
                    Batch("body_fat", t, t.copy(), np.round(fat * 100, 1), None, "day", chosen, lag_class="manual"),
                )
            )
    if persona.bp_cuff:
        chosen = days[rng.random(n) < 0.3]
        t = wake[chosen] + rng.uniform(5, 60, len(chosen)) * MINUTE
        systolic = 115 + 0.45 * (persona.age - 40) + daily.systolic_delta[chosen] + rng.normal(0, 7, len(chosen))
        diastolic = 0.55 * systolic + 8 + rng.normal(0, 5, len(chosen))
        out.append(
            (
                "Health",
                Batch(
                    "blood_pressure_systolic", t, t.copy(), np.round(systolic), None, "day", chosen, lag_class="manual"
                ),
            )
        )
        out.append(
            (
                "Health",
                Batch(
                    "blood_pressure_diastolic",
                    t,
                    t.copy(),
                    np.round(diastolic),
                    None,
                    "day",
                    chosen,
                    lag_class="manual",
                ),
            )
        )
    if persona.height_logger:
        t = np.asarray([window[0] + float(rng.uniform(0, 20)) * 86400])
        out.append(
            (
                "Health",
                Batch(
                    "height",
                    t,
                    t.copy(),
                    np.asarray([round(persona.height_cm, 1)]),
                    None,
                    "day",
                    np.asarray([1]),
                    lag_class="manual",
                ),
            )
        )
    if persona.alcohol_drinks_per_day > 0:
        drinks = rng.poisson(
            persona.alcohol_drinks_per_day * (1 + 0.8 * np.isin([d.weekday() for d in daily.days], (4, 5)))
        )
        t = timeline.bed[days] - rng.uniform(1, 4, n) * HOUR
        out.append(
            (
                "Bevel",
                Batch("alcoholic_beverages", t, t.copy(), drinks.astype(float), None, "day", days, lag_class="manual"),
            )
        )
    if persona.nutrition_logger:
        meals_t, meals_d = [], []
        for d in days:
            for hour in (8.0, 13.0, 19.0):
                meals_t.append(wake[d] + (hour - 7.5) * HOUR + rng.normal(0, 0.6) * HOUR)
                meals_d.append(d)
            for _ in range(rng.poisson(1.2)):
                meals_t.append(wake[d] + rng.uniform(1, 14) * HOUR)
                meals_d.append(d)
        t = np.asarray(meals_t)
        d = np.asarray(meals_d)
        energy = rng.lognormal(np.log(550), 0.5, len(t))
        for metric, share, per_gram in (
            ("dietary_energy", 1.0, 1.0),
            ("dietary_protein", 0.2, 4.0),
            ("dietary_carbohydrates", 0.45, 4.0),
            ("dietary_fat", 0.35, 9.0),
        ):
            value = energy * share / per_gram * np.exp(rng.normal(0, 0.15, len(t)))
            out.append(
                ("Cronometer", Batch(metric, t, t.copy(), np.round(value, 2), None, "day", d, lag_class="manual"))
            )
        # Micronutrients per meal, scaled by meal energy (values per ~550 kcal meal).
        for metric, per_meal in (
            ("dietary_fiber", 8.0),
            ("dietary_sugar", 18.0),
            ("dietary_fat_saturated", 7.0),
            ("dietary_cholesterol", 90.0),
            ("dietary_sodium", 800.0),
            ("dietary_potassium", 900.0),
            ("dietary_calcium", 300.0),
            ("dietary_iron", 4.0),
            ("dietary_magnesium", 110.0),
            ("dietary_zinc", 3.5),
            ("dietary_vitamin_c", 25.0),
            ("dietary_vitamin_d", 1.5),
            ("dietary_vitamin_b12", 1.2),
        ):
            logged = rng.random(len(t)) < 0.85
            value = per_meal * energy / 550 * np.exp(rng.normal(0, 0.35, len(t)))
            out.append(
                (
                    "Cronometer",
                    Batch(
                        metric,
                        t[logged],
                        t[logged].copy(),
                        np.round(value[logged], 3),
                        None,
                        "day",
                        d[logged],
                        lag_class="manual",
                    ),
                )
            )
        water_t = np.sort(np.concatenate([wake[dd] + rng.uniform(0.5, 15, 6) * HOUR for dd in days]))
        water_d = np.searchsorted(wake, water_t, side="right") - 1
        out.append(
            (
                "Cronometer",
                Batch(
                    "dietary_water",
                    water_t,
                    water_t.copy(),
                    np.round(rng.uniform(150, 500, len(water_t))),
                    None,
                    "day",
                    np.clip(water_d, 0, n - 1),
                    lag_class="manual",
                ),
            )
        )
        caffeine_t = wake + rng.uniform(0.2, 1.5, n) * HOUR
        out.append(
            (
                "Cronometer",
                Batch(
                    "dietary_caffeine",
                    caffeine_t,
                    caffeine_t.copy(),
                    np.round(rng.uniform(60, 180, n), 1),
                    None,
                    "day",
                    days,
                    lag_class="manual",
                ),
            )
        )
    lo, hi = window
    return [(s, b.select((b.start >= lo) & (b.start < hi))) for s, b in out]
