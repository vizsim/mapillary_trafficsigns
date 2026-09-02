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
# 🔒 Nur ein Worker gleichzeitig
# ---------------------------
# ts (Mi 15:00) und mk (Do 01:00) teilen sich Compose-Projekt, gluetun, output/
# und den git-Index. `docker compose down` weiter unten ist projektweit: startet
# mk, während ts noch läuft (nach VPN-Hängern mit langen Nachläufen durchaus
# möglich), reißt es den ts-Lauf mit. Deshalb ein Lock — und bei Kollision
# sichtbar aussteigen statt still zu kollidieren.
LOCK_FILE="${MAPILLARY_WORKER_LOCK:-/tmp/mapillary_worker.lock}"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "⏭️  Anderer Worker läuft noch (Lock $LOCK_FILE) — $SERVICE wird übersprungen, kein Commit."
  exit 0
fi

# Obergrenze für den Worker-Lauf. Normal sind ~6 h. Hängt der Lauf (gestrandete
# Sockets nach VPN-Reconnect, beobachtet 2026-07-01), würde er sonst über das
# Lock jeden folgenden Worker blockieren. Bereits exportierte Bundesländer
# bleiben erhalten — der Export passiert pro Land.
WORKER_TIMEOUT="${WORKER_TIMEOUT:-16h}"

# ---------------------------
# 🌐 Compose-Setup
# ---------------------------
DC="docker compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"

# Cleanup bei Exit (auch bei Fehler). Vorher die gluetun-Logs sichern: Compose
# hängt nur an den Worker-Logs, VPN-Reconnects und Exit-IPs standen bisher
# nirgends — beim Lauf vom 26.08. war deshalb nicht rekonstruierbar, was das
# VPN getan hat.
cleanup() {
  mkdir -p logs
  docker logs gluetun > "logs/gluetun-${SERVICE}.log" 2>&1 || true
  $DC down --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# Container aufräumen
$DC down --remove-orphans

# ---------------------------
# 🔎 Preflight: ist das Working Directory sauber?
# ---------------------------
# Ist beim Start schon was uncommitted, liegt vermutlich Müll eines
# fehlgeschlagenen Vorlaufs herum (z. B. nach OOM-Abbruch). Nur WARNEN, kein
# automatisches `reset --hard` — das würde echte Zwischenstände zerstören.
# Task 1 begrenzt den Commit-Scope ohnehin, hier geht es nur um Sichtbarkeit.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "⚠️  Working Directory ist beim Start nicht sauber:"
  git status --short
  echo "⚠️  Reste werden NICHT automatisch committet — bei Bedarf prüfen/aufräumen."
fi

# ---------------------------
# 🐳 Worker-Service starten
# ---------------------------
# Compose startet gluetun automatisch mit hoch und wartet auf den
# Healthcheck (depends_on: condition: service_healthy in docker-compose.vpn.yml).
echo "Starte Worker: $SERVICE (gluetun wird automatisch hochgefahren, Limit $WORKER_TIMEOUT)"
timeout --signal=INT --kill-after=5m "$WORKER_TIMEOUT" \
  $DC up --build --abort-on-container-exit --exit-code-from "$SERVICE" "$SERVICE" || {
  rc=$?
  if [[ $rc -eq 124 ]]; then
    echo "❌ Worker nach $WORKER_TIMEOUT abgebrochen (Hänger?) — skippe Auto-Commit"
  else
    echo "❌ Worker-Fehler (Exit $rc) — skippe Auto-Commit"
  fi
  exit 1
}

# ---------------------------
# ☁️ Schwere Outputs nach B2 archivieren (nicht in git)
# ---------------------------
# Unabhängig vom git-Commit: läuft auch, wenn es keine Notebook-/Metadata-Diffs
# gibt. Defensive — fehlt b2/Creds, wird nur gewarnt (bricht den Lauf nicht).
"$(dirname "$0")/upload_outputs_to_b2.sh" "$SERVICE" || \
  echo "⚠️  B2-Upload meldete einen Fehler — Lauf wird trotzdem fortgesetzt."

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
# Jeden Pfad einzeln stagen. Ein fehlender Pfad ist harmlos (überspringen).
# Ein echter git-Fehler (index.lock eines parallelen Laufs, Rechte) ist es
# nicht: vorher wurde beides als "kein Treffer" gemeldet und mit einem
# Teil-Staging weitercommittet.
for p in "${COMMIT_PATHS[@]}"; do
  if [[ ! -e "$p" ]]; then
    echo "⚠️  Pfad '$p' existiert nicht — übersprungen"
    continue
  fi
  git add -- "$p" || {
    echo "❌ git add '$p' fehlgeschlagen (index.lock? Rechte?) — Auto-Commit abgebrochen"
    exit 1
  }
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
