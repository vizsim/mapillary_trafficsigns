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

# ---------------------------
# 📦 Nur worker-eigene Pfade stagen
# ---------------------------
# WICHTIG: kein `git add -A`. Sonst werden liegengebliebene Dateien des ANDEREN
# Workers (z. B. Reste eines fehlgeschlagenen Vorlaufs) mit committet.
# Gescoped wird auf Verzeichnis-Ebene, damit neue Output-Dateien automatisch
# erfasst werden, ohne dass diese Liste gepflegt werden muss.
case "$SERVICE" in
  mapillary-ts_worker)
    COMMIT_PATHS=(
      "2_get_mapillary_traffic_signs.ipynb"
      # ts-Parquets sind in .gitignore (Zwischendaten, -> B2) und werden bewusst
      # NICHT committet. Nur das kleine Metadata-JSON bleibt als Lauf-Protokoll.
      "output/ml-ts_metadata.json"
      "use_cases/cycleway_complete_campaign"
    )
    ;;
  mapillary-mk_worker)
    # mk-Outputs in output/ sind in .gitignore ausgeschlossen → kein output/-Eintrag.
    COMMIT_PATHS=(
      "2b_get_mapillary_map_feature_points.ipynb"
      "use_cases/cycleway_complete_marking_campaign"
    )
    ;;
  *)
    echo "❌ Unbekannter Service '$SERVICE' — Auto-Commit abgebrochen"
    exit 2
    ;;
esac

echo "➕ Stage nur die Pfade von $SERVICE…"
# Jeden Pfad einzeln stagen. Ein Glob ohne Treffer lässt `git add` fehlschlagen
# und würde unter `set -e` den ganzen Lauf abbrechen → daher pro Pfad abfangen
# und sichtbar loggen (statt still zu maskieren).
for p in "${COMMIT_PATHS[@]}"; do
  git add -- $p || echo "⚠️  Kein Treffer für Pfad '$p' — übersprungen"
done

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
