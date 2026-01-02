#!/usr/bin/env bash
set -e

cd /app   # im Container ist /app dein Repo

# tqdm in Docker-Run deaktivieren, damit die Logs nicht zugespammt werden
export TQDM_DISABLE=1

echo "🚀 Starting"
echo

# Hintergrundprozess: RAM alle 5 Sekunden loggen
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


echo "🚀 Running Notebook: 2"


jupyter nbconvert \
  --to notebook \
  --inplace \
  --execute 2_get_mapillary_traffic_signs.ipynb

echo "✅ Notebook 2 execution finished"




# Logger stoppen
kill $LOGGER_PID || true


echo "done."