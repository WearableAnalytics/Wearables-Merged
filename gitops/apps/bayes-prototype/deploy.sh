#!/usr/bin/env bash
# Deploy (or redeploy) the Bayes prototype next to the wearables platform.
#
# Usage: BAYES_REPO=~/Desktop/charite [BAYES_REF=main] ./deploy.sh
#
# Copies a `git archive` of BAYES_REF (tracked files only, so no .env) onto the
# bayes-app PVC, builds it inside the cluster, then (re)starts the Deployment.
# If the API is only reachable through the de.NBI jumphost, open a SOCKS tunnel
# first and export HTTPS_PROXY=socks5://127.0.0.1:<port>.
set -euo pipefail

NS=bayes-prototype
HERE="$(cd "$(dirname "$0")" && pwd)"
BAYES_REPO="${BAYES_REPO:?set BAYES_REPO to a local clone of bayesimpact/charite}"
BAYES_REF="${BAYES_REF:-main}"

kubectl apply -f "$HERE/manifests.yaml"
kubectl -n "$NS" scale deploy/bayes-prototype --replicas=0
kubectl -n "$NS" wait --for=delete pod -l app=bayes-prototype --timeout=120s || true

kubectl -n "$NS" delete pod bayes-builder --ignore-not-found --wait
kubectl -n "$NS" apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: bayes-builder
  namespace: bayes-prototype
spec:
  restartPolicy: Never
  securityContext: { runAsUser: 1000, runAsGroup: 1000, fsGroup: 1000 }
  containers:
    - name: builder
      image: node:24-slim
      command: ["sleep", "3600"]
      env: [{ name: HOME, value: /tmp }]
      volumeMounts: [{ name: app, mountPath: /work }]
      resources: { requests: { cpu: 500m, memory: 1Gi }, limits: { memory: 3Gi } }
  volumes:
    - name: app
      persistentVolumeClaim: { claimName: bayes-app }
EOF
kubectl -n "$NS" wait --for=condition=Ready pod/bayes-builder --timeout=300s

archive="$(mktemp -t bayes-src.XXXXXX).tar"
git -C "$BAYES_REPO" archive --format=tar -o "$archive" "$BAYES_REF"
kubectl -n "$NS" exec bayes-builder -- sh -c 'rm -rf /work/app /work/src.tar && mkdir -p /work/app'
kubectl -n "$NS" cp "$archive" bayes-builder:/work/src.tar
rm -f "$archive"

kubectl -n "$NS" exec bayes-builder -- sh -c '
  set -e
  cd /work/app && tar -xf /work/src.tar && rm /work/src.tar
  npm ci --no-audit --no-fund
  npm run build
  npm run build:mcp-apps
  npm run db:setup
'

kubectl -n "$NS" delete pod bayes-builder --wait
kubectl -n "$NS" scale deploy/bayes-prototype --replicas=1
kubectl -n "$NS" rollout status deploy/bayes-prototype --timeout=300s
echo "Deployed $(git -C "$BAYES_REPO" rev-parse --short "$BAYES_REF") to namespace $NS"
