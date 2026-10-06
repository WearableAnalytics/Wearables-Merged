#!/bin/sh
# Usage: helm upgrade ... --post-renderer ./post-render/post-render.sh
set -eu
dir="$(cd "$(dirname "$0")" && pwd)"
cat > "$dir/all.yaml"
kustomize build "$dir"
rm -f "$dir/all.yaml"
