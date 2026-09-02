#!/usr/bin/env bash
# Führt die Notebook-Kette EINER Pipeline im Worker-Container aus.
#
#   run_mapillary_notebooks.sh ts   -> Traffic Signs
#   run_mapillary_notebooks.sh mk   -> Map Feature Points (Markierungen)
#
# Ersetzt run_mapillary-ts_notebooks.sh und run_mapillary-mk_notebooks.sh, die
# bis auf drei Notebook-Pfade byteidentisch waren - und deren Argument ("ts"/
# "mk" aus docker-compose.yml) keines der beiden je gelesen hat.
set -euo pipefail

PIPELINE="${1:-}"
case "$PIPELINE" in
  ts)
    NOTEBOOKS=(
      "2_get_mapillary_traffic_signs.ipynb"
      "use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb"
      "use_cases/cycleway_complete_campaign/2_create_pmtiles_from_geojson_trafficsigns.ipynb"
    )
    ;;
  mk)
    NOTEBOOKS=(
      "2b_get_mapillary_map_feature_points.ipynb"
      "use_cases/cycleway_complete_marking_campaign/x_mapillary-markings_generateOutput_2radinfra.ipynb"
      "use_cases/cycleway_complete_marking_campaign/2_create_pmtiles_from_geojson_markings.ipynb"
    )
    ;;
  *)
    echo "❌ Pipeline angeben: ts | mk (bekommen: '$PIPELINE')"
    exit 2
    ;;
esac

# Im Container liegt das Repo unter /app (Bind-Mount); lokal funktioniert das
# Script aus dem Repo-Root heraus genauso.
cd "${APP_DIR:-/app}" 2>/dev/null || cd "$(dirname "$0")/.."
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

# Ausgeführte Kopien landen unter logs/executed/ (gitignored) statt in-place:
# die getrackten Notebooks bleiben unverändert, der Working Tree sauber. Der
# Kernel läuft trotzdem im Verzeichnis des Quell-Notebooks, relative Pfade
# (../../output, ts_output/) funktionieren wie bisher.
EXECUTED_DIR="logs/executed"
mkdir -p "$EXECUTED_DIR"

echo "🚦 Pipeline $PIPELINE: ${#NOTEBOOKS[@]} Notebooks (ausgeführte Kopien: $EXECUTED_DIR/)"
echo

for nb in "${NOTEBOOKS[@]}"; do
  echo "▶️  $nb"
  jupyter nbconvert --to notebook --execute "$nb" \
    --output-dir "$EXECUTED_DIR" --output "$(basename "$nb")"
  echo "✅ $nb"
  echo
  maybe_sleep "$SLEEP_BETWEEN_STEPS"
  maybe_drop_caches
done

echo "done."
