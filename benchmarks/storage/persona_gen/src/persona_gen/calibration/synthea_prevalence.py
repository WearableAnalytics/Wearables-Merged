"""Age-band prevalence of the conditions in ``clinical.toml`` in a Synthea roster.

Counts adults alive on the reference date who have a matching condition active on that date (matched with the
``pattern`` regexes of ``clinical.toml``), per age band. Prints ``prevalence_by_age`` rows at band midpoints, so
the fallback sampler can be kept consistent with what a Synthea roster contains. Synthea models diagnosed
conditions, so these are diagnosed prevalences.

Usage: python -m persona_gen.calibration.synthea_prevalence DIR [--reference 2026-01-01]
"""

import argparse
import csv
import re
import tomllib
from datetime import date
from pathlib import Path

PARAMS = Path(__file__).resolve().parent.parent / "params" / "clinical.toml"
DENSE_BANDS = [(18, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 100)]
# Conditions with few cases in a roster of a few thousand: coarser bands keep the rates from jumping around.
COARSE_BANDS = [(18, 50), (50, 65), (65, 80), (80, 100)]


def prevalence(csv_dir: Path, reference: date, bands: list[tuple[int, int]], pattern: str):
    """Return ``[(band_midpoint, prevalence, adults, cases), ...]`` for one condition pattern."""
    ages: dict[str, float] = {}
    with open(csv_dir / "patients.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["DEATHDATE"] and date.fromisoformat(row["DEATHDATE"]) <= reference:
                continue
            age = (reference - date.fromisoformat(row["BIRTHDATE"])).days / 365.25
            if age >= 18:
                ages[row["Id"]] = age
    rx = re.compile(pattern, re.IGNORECASE)
    with_condition: set[str] = set()
    with open(csv_dir / "conditions.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["PATIENT"] not in ages or not rx.search(row["DESCRIPTION"]):
                continue
            if date.fromisoformat(row["START"]) <= reference and (
                not row["STOP"] or date.fromisoformat(row["STOP"]) > reference
            ):
                with_condition.add(row["PATIENT"])
    out = []
    for lo, hi in bands:
        group = [p for p, a in ages.items() if lo <= a < hi]
        cases = sum(p in with_condition for p in group)
        out.append(((lo + min(hi, 90)) / 2, cases / len(group) if group else 0.0, len(group), cases))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_dir", type=Path)
    parser.add_argument("--reference", type=date.fromisoformat, default=date(2026, 1, 1))
    args = parser.parse_args()
    conditions = tomllib.loads(PARAMS.read_text())["conditions"]
    for name, spec in conditions.items():
        for label, bands in (("dense", DENSE_BANDS), ("coarse", COARSE_BANDS)):
            rows = prevalence(args.csv_dir, args.reference, bands, spec["pattern"])
            cells = ", ".join(f"[{mid:g}, {p:.3f}]" for mid, p, _, _ in rows)
            cases = sum(r[3] for r in rows)
            print(f"{name} ({label}, {cases} cases): prevalence_by_age = [{cells}]")


if __name__ == "__main__":
    main()
