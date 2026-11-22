#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker compose up -d --build
api=http://127.0.0.1:18010
attempt=0
until curl -fsS "$api/health" >/dev/null &&
      curl -fsS http://127.0.0.1:19090/api/v1/query --data-urlencode 'query=up{job="extraction-service"} == 1' |
      python3 -c 'import json,sys; sys.exit(not json.load(sys.stdin)["data"]["result"])'; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        docker compose logs --tail=30
        exit 1
    fi
    sleep 2
done
for i in 1 2 3; do
    curl -fsS "$api/v1/measurements/export.csv" >/dev/null
    curl -fsS "$api/v1/measurements/export.fhir" >/dev/null
    status=$(curl -sS -o /dev/null -w '%{http_code}' "$api/v1/measurements/export.csv?start=invalid")
    test "$status" = 422
    # The upstream exception occurs after response headers have been sent.
    if curl -fsS "$api/v1/measurements/export.csv?measurement=demo-upstream-failure" >/dev/null; then
        echo "Expected a failed CSV stream" >&2
        exit 1
    fi
    sleep 5
done
curl -fsS http://127.0.0.1:19103/metrics | grep '^wearables_export_completed_total'
echo 'Grafana http://127.0.0.1:13000/d/wearables-export-monitoring'
echo 'Prometheus http://127.0.0.1:19090/targets'
