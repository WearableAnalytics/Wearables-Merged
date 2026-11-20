#!/usr/bin/env bash
set -euo pipefail

dataset="pacific28/apple-health-data"
destination="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uvx >/dev/null 2>&1; then
  echo "uvx is required; install uv from https://docs.astral.sh/uv/" >&2
  exit 1
fi

uvx --with six 'kaggle==2.2.5' datasets download \
  -d "$dataset" -p "$destination" --unzip

python3 - "$dataset" "$destination/dataset-metadata.json" <<'PY'
import json
import sys
from urllib.request import urlopen

dataset, output_path = sys.argv[1], sys.argv[2]
url = f"https://www.kaggle.com/api/v1/datasets/view/{dataset}"

with urlopen(url) as response:
    metadata = json.load(response)

with open(output_path, "w", encoding="utf-8") as output:
    json.dump(metadata, output, ensure_ascii=False, indent=2)
    output.write("\n")
PY