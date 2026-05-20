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
# 🌐 Compose-Setup
# ---------------------------
DC="docker compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"

# Cleanup bei Exit (auch bei Fehler)
trap '$DC down --remove-orphans 2>/dev/null || true' EXIT

# Container aufräumen
$DC down --remove-orphans

# ---------------------------
# 🐳 Worker-Service starten
# ---------------------------
# Compose startet gluetun automatisch mit hoch und wartet auf den
# Healthcheck (depends_on: condition: service_healthy in docker-compose.vpn.yml).
echo "Starte Worker: $SERVICE (gluetun wird automatisch hochgefahren)"
$DC up --build --abort-on-container-exit --exit-code-from "$SERVICE" "$SERVICE" || {
  echo "❌ Worker-Fehler — skippe Auto-Commit"
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
