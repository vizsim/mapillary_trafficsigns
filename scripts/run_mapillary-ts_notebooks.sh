#!/usr/bin/env bash
set -euo pipefail

cd /app
export TQDM_DISABLE=1

# Optional pacing / memory housekeeping.
# - Set SLEEP_BETWEEN_STEPS=10 to sleep 10s between major steps.
# - Set DROP_CACHES=1 to attempt to drop Linux page cache (requires privileges; otherwise no-op).
SLEEP_BETWEEN_STEPS=${SLEEP_BETWEEN_STEPS:-0}
DROP_CACHES=${DROP_CACHES:-0}

maybe_sleep() {
  local seconds="${1:-0}"
  if [[ "$seconds" =~ ^[0-9]+$ ]] && (( seconds > 0 )); then
    echo "⏳ Sleeping ${seconds}s…"
    sleep "$seconds"
  fi
}

maybe_drop_caches() {
  if [[ "$DROP_CACHES" != "1" ]]; then
    return 0
  fi

  # This only drops filesystem page cache (not anonymous RSS) and usually requires root/CAP_SYS_ADMIN.
  if [[ -w /proc/sys/vm/drop_caches ]]; then
    echo "🧹 Dropping Linux page cache…"
    sync || true
    echo 3 > /proc/sys/vm/drop_caches || true
  else
    echo "ℹ️  DROP_CACHES=1 set, but no permission to write /proc/sys/vm/drop_caches (skipping)."
  fi
}


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

maybe_sleep "$SLEEP_BETWEEN_STEPS"
maybe_drop_caches

echo "🚦 Running generateOutput_2radinfra"

jupyter nbconvert \
  --to notebook \
  --inplace \
  --execute use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb
            

echo "✅ generateOutput_2radinfra execution finished"


maybe_sleep "$SLEEP_BETWEEN_STEPS"
maybe_drop_caches


echo "🚦 Running create PMTiles from geojson"

jupyter nbconvert \
  --to notebook \
  --inplace \
  --execute use_cases/cycleway_complete_campaign/2_create_pmtiles_from_geojson_trafficsigns.ipynb

echo "✅ 2_create_pmtiles_from_geojson_trafficsigns execution finished"

maybe_sleep "$SLEEP_BETWEEN_STEPS"
maybe_drop_caches


echo "done."