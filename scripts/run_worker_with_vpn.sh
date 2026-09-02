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
# 📝 Lauf-Protokoll
# ---------------------------
# Kein Auto-Commit mehr (seit 2026-09-02). Die Daten landen auf B2 /
# data.vizsim.de, die Lauf-Mitschrift liegt in logs/<pipeline>_run_latest.log,
# die ausgeführten Notebook-Kopien in logs/executed/. Nichts davon ist getrackt,
# der Working Tree bleibt sauber und `git pull` auf dem Server geht ohne Reset.
# Vorher wuchsen die Notebooks mit Outputs (bis 17,5 MB) und pmtiles/gz
# (~34 MB/Woche) in die History - siehe git-history-rewrite 2026-07.
echo
echo "📝 Lauf-Bilanz ($SERVICE):"
for f in logs/*_run_latest.log; do
  [[ -e "$f" ]] && grep -aE "Lauf beendet|Nicht aktualisiert|NICHT exportiert" "$f" | sed 's/^/   /'
done
echo "🎉 Fertig!"
