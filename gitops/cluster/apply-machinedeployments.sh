#!/usr/bin/env bash
# Renders the Kubermatic MachineDeployments (node pools) and diffs or applies them.
#
#   CLUSTER_ENV=path/to/cluster.env ./apply-machinedeployments.sh          # diff only
#   CLUSTER_ENV=path/to/cluster.env ./apply-machinedeployments.sh --apply  # apply
#
# Any change below spec.template (flavor, disk, image, SSH keys, labels) makes
# Kubermatic replace every node of that pool, one at a time (maxSurge 1).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_ENV="${CLUSTER_ENV:-$SCRIPT_DIR/cluster.env}"
MODE="${1:-diff}"

if [[ ! -f "$CLUSTER_ENV" ]]; then
	echo "Missing $CLUSTER_ENV (copy cluster.env.example and fill it in)." >&2
	exit 1
fi
# shellcheck disable=SC1090
source "$CLUSTER_ENV"
: "${KKP_CLUSTER_ID:?}" "${KKP_PROJECT_ID:?}" "${OS_SUBNET_ID:?}"
SSH_KEYS_DIR="${SSH_KEYS_DIR:-}"

render() {
	local file="$1" name keys="[]"
	name="$(basename "$file" .yaml)"
	if [[ -n "$SSH_KEYS_DIR" && -f "$SSH_KEYS_DIR/$name.json" ]]; then
		keys="$(tr -d '\n' <"$SSH_KEYS_DIR/$name.json")"
	fi
	SSH_PUBLIC_KEYS_JSON="$keys" KKP_CLUSTER_ID="$KKP_CLUSTER_ID" KKP_PROJECT_ID="$KKP_PROJECT_ID" OS_SUBNET_ID="$OS_SUBNET_ID" \
		envsubst '${KKP_CLUSTER_ID} ${KKP_PROJECT_ID} ${OS_SUBNET_ID} ${SSH_PUBLIC_KEYS_JSON}' <"$file"
}

for file in "$SCRIPT_DIR"/machinedeployments/*.yaml; do
	echo "== $(basename "$file" .yaml)"
	if [[ "$MODE" == "--apply" ]]; then
		render "$file" | kubectl apply -f -
	else
		render "$file" | kubectl diff -f - || true
	fi
done
