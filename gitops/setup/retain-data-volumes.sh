#!/usr/bin/env bash
# Sets persistentVolumeReclaimPolicy=Retain on the PVs that hold platform data,
# so deleting a PVC (helm uninstall, namespace delete) keeps the Cinder volume.
# Idempotent. Pass --dry-run to only list what would change.
set -euo pipefail

# namespace/pvc-name-prefix of the data we must never lose
DATA_CLAIMS=(
	"prod-postgres/"
	"influx/"
	"kafka/data-"
	"prometheus/"
	"grafana/"
	"ml-pipeline-seaweedfs/"
	"infisical/"
	"bayes-platform/"
)

kubectl get pvc -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name} {.spec.volumeName}{"\n"}{end}' |
	while read -r claim pv; do
		[[ -z "$pv" ]] && continue
		for prefix in "${DATA_CLAIMS[@]}"; do
			if [[ "$claim" == "$prefix"* ]]; then
				policy="$(kubectl get pv "$pv" -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')"
				if [[ "$policy" != "Retain" ]]; then
					echo "Retain: $claim ($pv, was $policy)"
					if [[ "${1:-}" != "--dry-run" ]]; then
						kubectl patch pv "$pv" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}' >/dev/null
					fi
				fi
				break
			fi
		done
	done
