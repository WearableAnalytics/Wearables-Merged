#!/usr/bin/env python3
"""Copy the canonical numeric mapping, or check that its consumers match it."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    canonical = root / "services/backend/fhir-mapper-validator/config/mapping-2026-01-28.yaml"
    content = canonical.read_text()
    outputs = {
        "services/backend/fhir-mapper-validator/src/main/resources/mapping-2026-01-28.yaml": content,
        "services/backend/extraction-service/src/app/default_fhir_mapping.yaml": content,
        "gitops/apps/services/mapper-validator/templates/mappings-config-map.yaml": (
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {{ .Values.mappingConfig }}\n"
            "data:\n  mapping.yaml: |\n" + "".join("    " + line + "\n" for line in content.splitlines())
        ),
    }
    stale = []
    for name, expected in outputs.items():
        path = root / name
        if path.read_text() != expected:
            stale.append(name)
            if not args.check:
                path.write_text(expected)
    if args.check and stale:
        parser.exit(1, "Run scripts/sync-measurement-mapping.py to update:\n" + "\n".join(stale) + "\n")


if __name__ == "__main__":
    main()
