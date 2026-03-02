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

# Container aufräumen
$DC down --remove-orphans

# VPN-Container starten
echo "Starting gluetun..."
$DC up -d gluetun

# Auf VPN-Readiness warten (max. 5 Minuten)
echo "Waiting for VPN readiness..."
timeout 300 bash -c '
  until docker logs gluetun 2>&1 | grep -q "Initialization Sequence Completed"; do sleep 2; done
  until docker logs gluetun 2>&1 | grep -qi "dns.*ready"; do sleep 2; done
'

# ---------------------------
# 🐳 Worker-Service starten
# ---------------------------
echo "✅ VPN ready → starte Worker: $SERVICE"
$DC up --build "$SERVICE" || {
  echo "❌ Worker-Fehler — skippem Auto-Commit"
  exit 1
}

# ---------------------------
# 🔄 Auto-Commit nach erfolgreicher Ausführung
# ---------------------------
BRANCH="feature/docker-notebook"

if git diff --quiet && git diff --cached --quiet; then
  echo "ℹ️ Keine Änderungen — nichts zu committen."
  exit 0
fi

echo "➕ Füge alle Änderungen zum Commit hinzu..."
git add .

#COMMIT_MSG="Auto-update: worker $SERVICE outputs ($(date -Iseconds))"
COMMIT_MSG="Auto-update: outputs, notebooks, metadata ($(date -Iseconds))"

echo "✍️ Committe: $COMMIT_MSG"
git commit -m "$COMMIT_MSG"

echo "🚀 Push nach GitHub..."
git push origin "$BRANCH"

echo "🎉 Fertig!"