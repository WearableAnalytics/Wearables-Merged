"""Read a frozen Synthea CSV roster (patients, conditions, medications, encounters)."""

import hashlib
from collections import defaultdict
from csv import DictReader
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Entry:
    description: str
    code: str
    start: date
    stop: date | None


@dataclass(frozen=True, slots=True)
class SyntheaPatient:
    id: str
    birth: date
    death: date | None
    sex: str
    conditions: tuple[Entry, ...]
    medications: tuple[Entry, ...]
    inpatient: tuple[Entry, ...]

    def age_on(self, day: date) -> int:
        return day.year - self.birth.year - ((day.month, day.day) < (self.birth.month, self.birth.day))


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value.split("T", maxsplit=1)[0]) if value else None


def _entries(path: Path, *, inpatient: bool = False) -> dict[str, list[Entry]]:
    result: dict[str, list[Entry]] = defaultdict(list)
    if not path.is_file():
        return result
    with path.open(encoding="utf-8", newline="") as stream:
        for row in DictReader(stream):
            if inpatient and row.get("ENCOUNTERCLASS", "").lower() != "inpatient":
                continue
            start = _day(row["START"])
            if start is None:
                continue
            result[row["PATIENT"]].append(
                Entry(
                    row.get("DESCRIPTION", "") or "",
                    row.get("CODE", "") or "",
                    start,
                    _day(row.get("STOP")),
                )
            )
    return result


ROSTER_FILES = ("patients.csv", "conditions.csv", "medications.csv", "encounters.csv")


def roster_identity(directory: Path) -> dict[str, object]:
    """SHA-256 over the roster CSVs and the patient count, so manifests tell rosters apart.

    The directory name is not part of it: the same roster in another place is the same roster.
    """
    directory = Path(directory)
    if not (directory / "patients.csv").exists():
        raise FileNotFoundError(f"No Synthea roster at {directory} (patients.csv missing)")
    digest = hashlib.sha256()
    files = []
    for name in ROSTER_FILES:
        path = directory / name
        if not path.exists():
            continue
        files.append(name)
        digest.update(name.encode() + b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                digest.update(chunk)
        digest.update(b"\0")
    with (directory / "patients.csv").open(encoding="utf-8", newline="") as stream:
        patients = sum(1 for _ in DictReader(stream))
    return {"sha256": digest.hexdigest(), "patients": patients, "files": files}


def load_roster(directory: Path) -> list[SyntheaPatient]:
    conditions = _entries(directory / "conditions.csv")
    medications = _entries(directory / "medications.csv")
    inpatient = _entries(directory / "encounters.csv", inpatient=True)
    patients: list[SyntheaPatient] = []
    with (directory / "patients.csv").open(encoding="utf-8", newline="") as stream:
        for row in DictReader(stream):
            key = row["Id"]
            birth = _day(row["BIRTHDATE"])
            if birth is None:
                continue
            patients.append(
                SyntheaPatient(
                    id=key,
                    birth=birth,
                    death=_day(row.get("DEATHDATE")),
                    sex=row["GENDER"].upper()[:1],
                    conditions=tuple(sorted(conditions[key], key=lambda e: (e.start, e.code))),
                    medications=tuple(sorted(medications[key], key=lambda e: (e.start, e.code))),
                    inpatient=tuple(sorted(inpatient[key], key=lambda e: (e.start, e.code))),
                )
            )
    if not patients:
        raise ValueError(f"No patients in Synthea roster {directory}")
    return sorted(patients, key=lambda p: p.id)


def synthea_command(
    jar: Path,
    out: Path,
    *,
    population: int,
    seed: int,
    reference: date,
    java: str = "java",
    state: str = "Massachusetts",
    ages: tuple[int, int] = (18, 90),
    modules: Path | None = None,
    max_heap: str = "2g",
) -> list[str]:
    command = [
        java,
        f"-Xmx{max_heap}",
        "-jar",
        str(jar),
        "-p",
        str(population),
        "-s",
        str(seed),
        "-cs",
        str(seed),
        "-r",
        reference.strftime("%Y%m%d"),
        "-a",
        f"{ages[0]}-{ages[1]}",
        "--exporter.csv.export",
        "true",
        "--exporter.fhir.export",
        "false",
        "--exporter.hospital.fhir.export",
        "false",
        "--exporter.practitioner.fhir.export",
        "false",
        "--exporter.baseDirectory",
        str(out),
    ]
    if modules is not None:
        command += ["-d", str(modules)]
    return [*command, state]


def run_synthea(
    jar: Path,
    out: Path,
    *,
    population: int,
    seed: int,
    reference: date,
    java: str = "java",
    state: str = "Massachusetts",
    ages: tuple[int, int] = (18, 90),
    modules: Path | None = None,
    max_heap: str = "2g",
) -> Path:
    """Run the Synthea JAR and return the CSV directory to pass as ``synthea_dir``."""
    import subprocess

    if (out / "csv").exists():
        raise FileExistsError(out / "csv")
    command = synthea_command(
        jar,
        out,
        population=population,
        seed=seed,
        reference=reference,
        java=java,
        state=state,
        ages=ages,
        modules=modules,
        max_heap=max_heap,
    )
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return out / "csv"
