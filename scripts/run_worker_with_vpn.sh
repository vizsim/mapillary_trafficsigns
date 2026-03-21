#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# ---------------------------
# ⚙️ Eingabevalidierung
# ---------------------------
SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "❌ Missing service name"
  exit 2
fi

# ---------------------------
# 🌐 VPN-Setup mit Gluetun
# ---------------------------
DC="docker-compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"

# Cleanup bei Exit (auch bei Fehler)
trap '$DC down --remove-orphans 2>/dev/null || true' EXIT

# Container aufräumen
$DC down --remove-orphans

# VPN-Container starten
echo "Starting gluetun..."
$DC up -d gluetun

# Auf VPN-Readiness warten (max. 5 Minuten)
echo "Waiting for VPN readiness..."
deadline=$(( $(date +%s) + 300 ))
while true; do
  vpn_status=$(docker inspect --format='{{.State.Health.Status}}' gluetun 2>/dev/null || true)
  if [[ "$vpn_status" == "healthy" ]]; then
    echo "✅ VPN healthy"
    break
  fi
  if (( $(date +%s) >= deadline )); then
    echo "❌ Timeout: gluetun not healthy after 5 min (last status: ${vpn_status:-unknown})"
    exit 1
  fi
  sleep 3
done

# ---------------------------
# 🐳 Worker-Service starten
# ---------------------------
echo "✅ VPN ready → starte Worker: $SERVICE"
$DC up --build --abort-on-container-exit --exit-code-from "$SERVICE" "$SERVICE" || {
  echo "❌ Worker-Fehler — skippem Auto-Commit"
  exit 1
}

# ---------------------------
# 🔄 Auto-Commit nach erfolgreicher Ausführung
# ---------------------------
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

echo "➕ Füge alle Änderungen zum Commit hinzu..."
git add -A

if git diff --cached --quiet; then
  echo "ℹ️ Keine Änderungen — nichts zu committen."
  exit 0
fi

COMMIT_MSG="Auto-update [$SERVICE]: outputs, notebooks, metadata ($(date -Iseconds))"

echo "✍️ Committe: $COMMIT_MSG"
git commit -m "$COMMIT_MSG"

echo "🚀 Push nach GitHub..."
git push origin "$BRANCH"

echo "🎉 Fertig!"