#!/usr/bin/env bash
set -euo pipefail

cd /app
export TQDM_DISABLE=1

# ---- RAM logger ----
(
  while true; do
    ts=$(date +"%H:%M:%S")
    mem=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || cat /sys/fs/cgroup/memory/memory.usage_in_bytes)
    mem_mb=$(awk "BEGIN {printf \"%.2f\", $mem/1024/1024}")
    echo "[$ts] RAM usage: ${mem_mb} MB"
    sleep 5
  done
) &
LOGGER_PID=$!
trap 'kill $LOGGER_PID 2>/dev/null || true' EXIT

echo "🚦 Running Mapillary Traffic Signs pipeline"
echo

jupyter nbconvert \
  --to notebook \
  --inplace \
  --execute 2_get_mapillary_traffic_signs.ipynb

echo "✅ Traffic Signs notebook finished"

echo "done."