"""``persona-gen``: generate synthetic persona datasets and handle the real calibration sources.

persona-gen generate --personas 100 --days 28 --out .local/personas
persona-gen generate --personas 100 --days 28 --events --out .local/personas-events
persona-gen generate --personas 100 --days 28 --synthea .local/synthea/csv --out .local/personas-clinical
persona-gen convert-calibration lifesnaps "$BENCH_LIFESNAPS_BSON" .local/calibration/raw/lifesnaps
persona-gen adapt-calibration kaggle .local/calibration/raw/kaggle .local/calibration/observed/kaggle
persona-gen fit-zepp-overlay  # optional: generate builds and caches it when the Kaggle file is present
persona-gen validate-storage --real .local/calibration/observed/kaggle --fixture .local/personas --device zepp_amazfit
"""

import argparse
import json
import os
from datetime import date
from pathlib import Path


def _generate(args: argparse.Namespace) -> int:
    from persona_gen import SyntheticRecipe, estimate_rows, generate_dataset, load_params, open_dataset

    overlays = [Path(p) for p in args.overlay]
    if args.events and args.synthea is not None:
        raise SystemExit("--events is a wearable-only variant; clinical datasets always have everyday events")
    if (args.wearable_only or args.events) and load_params(overlays=overlays)["cohorts"]["anchors"]["share"]:
        raise SystemExit("--wearable-only and --events require anchor share 0")
    recipe = SyntheticRecipe(
        date.fromisoformat(args.start),
        args.days,
        args.personas,
        args.seed,
        everyday_events=True if args.events else None,
    )
    synthea = Path(args.synthea) if args.synthea is not None else None
    if args.estimate:
        estimate = estimate_rows(
            recipe,
            overlays=overlays,
            synthea_dir=synthea,
            fitted_defaults=not args.no_fitted_defaults,
            kaggle_csv=args.kaggle_csv,
        )
        print(json.dumps(estimate, indent=2))
        return 0
    manifest = generate_dataset(
        Path(args.out),
        recipe,
        overlays=overlays,
        synthea_dir=synthea,
        workers=args.workers or os.cpu_count() or 1,
        fitted_defaults=not args.no_fitted_defaults,
        kaggle_csv=args.kaggle_csv,
    )
    dataset = open_dataset(manifest.parent)
    print(f"{manifest.parent}  {dataset.manifest['tables']['observations']:,} observations")
    if roster := dataset.manifest.get("synthea_roster"):
        personas = dataset.table("personas").to_pylist()
        linked = sum(1 for p in personas if p["synthea_id"])
        reused = sum(1 for p in personas if p["synthea_reused"])
        print(
            f"Synthea roster {roster['sha256'][:16]} ({roster['patients']:,} patients): "
            f"{linked}/{len(personas)} personas linked, {reused} reuse a patient"
        )
    return 0


def _convert_calibration(args: argparse.Namespace) -> int:
    from persona_gen.sources.raw import convert_kaggle, convert_lifesnaps

    if args.source == "lifesnaps":
        result = convert_lifesnaps(args.input, args.out, participant_index=args.participant_index, workers=args.workers)
    else:
        if args.participant_index is not None:
            raise SystemExit("--participant-index is only available for LifeSnaps")
        result = convert_kaggle(args.input, args.out)
    print(f"{args.out}  {result['rows']:,} source records")
    return 0


def _adapt_calibration(args: argparse.Namespace) -> int:
    from persona_gen.sources.observations import adapt_observations

    result = adapt_observations(args.source, args.input, args.out, participant=args.participant)
    print(f"{args.out}  {result['rows']:,} comparable observations")
    return 0


def _fit_lifesnaps_device(args: argparse.Namespace) -> int:
    from persona_gen.validation.storage import fit_lifesnaps_device

    print(json.dumps(fit_lifesnaps_device(args.profile, args.out, seed=args.seed), indent=2))
    return 0


def _fit_zepp_overlay(args: argparse.Namespace) -> int:
    from persona_gen.calibration.zepp import ensure_zepp_overlay

    path = ensure_zepp_overlay(args.home, args.csv, force=args.force)
    if path is None:
        raise SystemExit("The Kaggle Apple Health file was not found; pass --csv or run its download.sh")
    print(path)
    return 0


def _validate_storage(args: argparse.Namespace) -> int:
    from persona_gen.validation.storage import storage_report

    report = storage_report(
        args.real, args.fixture, args.device, holdout_start=args.holdout_start, seed=args.seed, repeats=args.repeats
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(args.out)
    else:
        print(rendered, end="")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="persona-gen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate a synthetic persona dataset")
    g.add_argument("--personas", type=int, required=True)
    g.add_argument("--days", type=int, required=True)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--start", default="2026-01-01", help="first UTC date (ISO)")
    g.add_argument("--workers", type=int)
    g.add_argument("--out", help="target directory (required unless --estimate)")
    mode = g.add_mutually_exclusive_group()
    mode.add_argument(
        "--wearable-only",
        action="store_true",
        help="generate without a clinical timeline (default); plain, without colds, injuries, mood episodes or travel",
    )
    mode.add_argument(
        "--synthea",
        metavar="DIR",
        help="map personas onto a Synthea CSV roster (patients.csv, conditions.csv, medications.csv, ...)",
    )
    g.add_argument(
        "--events",
        action="store_true",
        help="wearable-only variant with colds, injuries, mood episodes and travel",
    )
    g.add_argument(
        "--overlay",
        action="append",
        default=[],
        metavar="TOML",
        help="parameter overlay file or directory, e.g. a cohort mix; repeatable",
    )
    g.add_argument("--estimate", action="store_true", help="only print estimated row counts")
    g.add_argument(
        "--no-fitted-defaults",
        action="store_true",
        help="skip overlays fitted from public data on this machine (the Zepp/Amazfit model from the Kaggle export)",
    )
    g.add_argument(
        "--kaggle-csv", type=Path, help="Kaggle Apple Health CSV (default: found above the working directory)"
    )
    g.set_defaults(func=_generate)

    convert = sub.add_parser("convert-calibration", help="preserve a local calibration source in Parquet")
    convert.add_argument("source", choices=["lifesnaps", "kaggle"])
    convert.add_argument("input", type=Path)
    convert.add_argument("out", type=Path)
    convert.add_argument("--participant-index", type=int, help="convert one LifeSnaps participant for a pilot")
    convert.add_argument("--workers", type=int, default=4)
    convert.set_defaults(func=_convert_calibration)

    adapt = sub.add_parser("adapt-calibration", help="adapt local records to the observation schema")
    adapt.add_argument("source", choices=["lifesnaps", "kaggle", "apple"])
    adapt.add_argument("input", type=Path, help="converted source directory or personal export archive")
    adapt.add_argument("out", type=Path)
    adapt.add_argument("--participant", default="personal", help="local alias for a personal archive")
    adapt.set_defaults(func=_adapt_calibration)

    fit = sub.add_parser("fit-lifesnaps-device", help="fit Fitbit device timing on the training participants")
    fit.add_argument("profile", type=Path)
    fit.add_argument("out", type=Path)
    fit.add_argument("--seed", type=int, default=42)
    fit.set_defaults(func=_fit_lifesnaps_device)

    zepp = sub.add_parser(
        "fit-zepp-overlay",
        help="fit the Zepp/Amazfit device overlay from the Kaggle export (generate does this automatically)",
    )
    zepp.add_argument("--csv", type=Path, help="Kaggle Apple Health CSV (default: found above the working directory)")
    zepp.add_argument("--home", type=Path, help="cache root (default: $PERSONA_GEN_HOME, $BENCH_HOME or .local)")
    zepp.add_argument("--force", action="store_true", help="re-fit even if the cached overlay is current")
    zepp.set_defaults(func=_fit_zepp_overlay)

    validate = sub.add_parser("validate-storage", help="compare dataset storage metrics to held-out real observations")
    validate.add_argument("--real", type=Path, required=True, help="adapted observation directory")
    validate.add_argument("--fixture", type=Path, action="append", required=True, help="dataset directory; repeatable")
    validate.add_argument("--device", required=True, help="device model, e.g. zepp_amazfit")
    validate.add_argument("--holdout-start", type=date.fromisoformat, help="first held-out local date")
    validate.add_argument("--seed", type=int, default=42, help="participant split and baseline seed")
    validate.add_argument("--repeats", type=int, default=24)
    validate.add_argument("--out", type=Path)
    validate.set_defaults(func=_validate_storage)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "generate" and not args.estimate and not args.out:
        raise SystemExit("generate needs --out")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
