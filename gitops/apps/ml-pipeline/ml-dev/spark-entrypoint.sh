#!/bin/bash
# Dual-mode entrypoint:
#   - Spark operator passes "driver" or "executor" as $1 → delegate to Spark's entrypoint
#   - Jupyter / interactive use → delegate to start.sh
#
# Spark is installed at /usr/local/spark (not /opt/spark) in the pyspark-notebook image.
SPARK_ENTRYPOINT="/usr/local/spark/kubernetes/dockerfiles/spark/entrypoint.sh"

case "$1" in
  driver|executor|submit)
    exec "$SPARK_ENTRYPOINT" "$@"
    ;;
  *)
    exec /usr/local/bin/start.sh "$@"
    ;;
esac
