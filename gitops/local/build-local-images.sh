#!/usr/bin/env bash
set -euo pipefail

# Builds the platform's own service images straight into the local minikube
# cluster. minikube builds them natively, so they match the machine's
# architecture (arm64 on Apple Silicon, amd64 on x86) without extra flags.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_PREFIX="wearables-local"
TAG="dev"

# service name -> build context (relative to the repo root)
SERVICES=(
  "wearables-bff:services/backend/wearables-bff"
  "db-lord:services/backend/db_lord"
  "extraction-service:services/backend/extraction-service"
  "importservice:services/backend/importservice"
  "mapper-validator:services/backend/fhir-mapper-validator"
  "grafana-proxy:services/backend/grafana-proxy"
  "web:services/web"
)

usage() {
  cat <<'EOF'
Usage:
  ./gitops/local/build-local-images.sh [service ...]

Builds the named services into minikube as wearables-local/<service>:dev,
or all of them when none are named.

Services: wearables-bff db-lord extraction-service importservice
          mapper-validator grafana-proxy web
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

context_for() {
  local name="$1" entry
  for entry in "${SERVICES[@]}"; do
    if [[ "${entry%%:*}" == "$name" ]]; then
      echo "${entry#*:}"
      return 0
    fi
  done
  return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v minikube >/dev/null 2>&1 || die "minikube is required"
minikube status >/dev/null 2>&1 || die "minikube is not running (start it with: minikube start)"

if [[ $# -gt 0 ]]; then
  selected=("$@")
else
  selected=()
  for entry in "${SERVICES[@]}"; do selected+=("${entry%%:*}"); done
fi

# Check all names before the first (slow) build.
for name in "${selected[@]}"; do
  context_for "$name" >/dev/null || die "unknown service: $name (see --help)"
done

for name in "${selected[@]}"; do
  image="${IMAGE_PREFIX}/${name}:${TAG}"
  echo "==> ${image}"
  log="$(mktemp)"
  minikube image build -t "$image" "${REPO_ROOT}/$(context_for "$name")" 2>&1 | tee "$log"
  # minikube image build exits 0 even when the build fails, so check its output.
  if grep -q '^ERROR' "$log"; then
    rm -f "$log"
    die "building ${image} failed"
  fi
  rm -f "$log"
done

echo "Built into minikube: ${selected[*]}"
