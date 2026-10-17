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
# 📟 Monitoring (healthchecks.io)
# ---------------------------
# Every run reports its start, then success or failure. The check also alerts
# when no run shows up at all (server down, cron broken). The ping URL is a
# secret and lives in docker/.env (HEALTHCHECK_URL_TS / HEALTHCHECK_URL_MK);
# without it, everything below is a no-op.
PIPELINE="${SERVICE#mapillary-}"; PIPELINE="${PIPELINE%_worker}"   # mapillary-ts_worker -> ts
RUN_LOG="logs/${PIPELINE}_run_latest.log"
RUN_START="$(date +%s)"
HC_VAR="HEALTHCHECK_URL_${PIPELINE^^}"
HC_URL="$(sed -nE "s/^${HC_VAR}=[\"']?([^\"'[:space:]]*)[\"']?[[:space:]]*$/\1/p" docker/.env 2>/dev/null | tail -1)"
HC_NOTE=""  # why the run failed; set right before the failing exit
DEPLOY_NOTE="${MAPILLARY_DEPLOY_NOTE:-}"  # what the deploy step did, if anything

# The run transcript of THIS run - not the one a previous run left behind.
run_log_is_current() {
  [[ -e "$RUN_LOG" ]] && (( $(stat -c %Y "$RUN_LOG") >= RUN_START ))
}

# hc_ping <suffix>: "/start", "/fail" or "" (success). Success and failure
# carry HC_NOTE plus the tail of the run transcript, so the dashboard shows
# what happened. Never fails the run itself.
hc_ping() {
  [[ -n "$HC_URL" ]] || return 0
  local body=""
  if [[ "$1" != "/start" ]]; then
    body="${DEPLOY_NOTE:+$DEPLOY_NOTE$'\n'}$HC_NOTE"
    if run_log_is_current; then
      body+=$'\n\n'"$(tail -n 40 "$RUN_LOG")"
    fi
  fi
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$body" "${HC_URL}$1" \
    || echo "⚠️  healthchecks.io not reachable (ping '${1:-success}')"
}

# ---------------------------
# 🔒 Nur ein Worker gleichzeitig
# ---------------------------
# ts (Mi 15:00) und mk (Do 01:00) teilen sich Compose-Projekt, gluetun, output/
# und den git-Index. `docker compose down` weiter unten ist projektweit: startet
# mk, während ts noch läuft (nach VPN-Hängern mit langen Nachläufen durchaus
# möglich), reißt es den ts-Lauf mit. Deshalb ein Lock — und bei Kollision
# sichtbar aussteigen statt still zu kollidieren.
LOCK_FILE="${MAPILLARY_WORKER_LOCK:-/tmp/mapillary_worker.lock}"
# After a deploy the script restarts itself and inherits fd 9 with the lock
# still held - taking it again would briefly release it.
if [[ -z "${MAPILLARY_LOCK_HELD:-}" ]]; then
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    echo "⏭️  Anderer Worker läuft noch (Lock $LOCK_FILE) — $SERVICE wird übersprungen."
    # A skipped run is a missed week for this pipeline - report it.
    HC_NOTE="Skipped: another worker still holds the lock ($LOCK_FILE)."
    hc_ping /fail
    exit 0
  fi
fi

# ---------------------------
# 🔄 Deploy: follow main, but only to a tested commit
# ---------------------------
# A push to main used to need a manual `git pull` on the server. Now every run
# fast-forwards to origin/main itself - but only if the CI run for that very
# commit (.github/workflows/tests.yml) succeeded. Otherwise it keeps the
# current code and says why in the final healthchecks.io ping: tests still
# running or failed, local changes, diverged history, GitHub unreachable.
#
# This happens after taking the lock, so it never changes files under another
# worker's feet. After an update the script restarts itself, so the new version
# of this very file is what runs. The block is a single `if`, which bash reads
# completely before running any of it - the update cannot change the rest of
# the block under the running shell. MAPILLARY_AUTO_DEPLOY=0 switches it off.

# ci_state <sha>: success | pending | failure | unknown, from GitHub's check runs.
ci_state() {
  local json
  json="$(curl -fsS -m 20 -H "Accept: application/vnd.github+json" \
    "${GITHUB_API:-https://api.github.com}/repos/${REPO_SLUG}/commits/$1/check-runs" 2>/dev/null)" \
    || { echo unknown; return 0; }
  python3 -c '
import json, sys
try:
    runs = json.loads(sys.stdin.read())["check_runs"]
except Exception:
    print("unknown"); sys.exit()
if not runs or any(r["status"] != "completed" for r in runs):
    print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("success")
else:
    print("failure")
' <<<"$json"
}

if [[ -z "${MAPILLARY_DEPLOYED:-}" && "${MAPILLARY_AUTO_DEPLOY:-1}" == 1 ]]; then
  REPO_SLUG="${MAPILLARY_REPO_SLUG:-$(git remote get-url origin | sed -nE 's#.*github\.com[:/]([^/]+/[^/.]+)(\.git)?$#\1#p')}"
  head_sha="$(git rev-parse HEAD)"
  if ! git fetch -q origin main 2>/dev/null; then
    DEPLOY_NOTE="Deploy: git fetch failed - staying on ${head_sha:0:7}."
  else
    target="$(git rev-parse origin/main)"
    if [[ "$head_sha" == "$target" ]]; then
      :  # already up to date
    elif ! git merge-base --is-ancestor HEAD "$target"; then
      DEPLOY_NOTE="Deploy: local history diverged from origin/main - staying on ${head_sha:0:7}."
    elif [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
      DEPLOY_NOTE="Deploy: local changes in tracked files - staying on ${head_sha:0:7}."
    else
      ci="$(ci_state "$target")"
      if [[ "$ci" != success ]]; then
        DEPLOY_NOTE="Deploy: CI for ${target:0:7} is ${ci} - staying on ${head_sha:0:7}."
      elif ! git merge -q --ff-only "$target"; then
        DEPLOY_NOTE="Deploy: fast-forward to ${target:0:7} failed - staying on ${head_sha:0:7}."
      else
        echo "🔄 Aktualisiert: ${head_sha:0:7} -> ${target:0:7} (CI grün), starte neu"
        exec env MAPILLARY_DEPLOYED=1 MAPILLARY_LOCK_HELD=1 \
          MAPILLARY_DEPLOY_NOTE="Deploy: updated ${head_sha:0:7} -> ${target:0:7} (CI green)." \
          bash scripts/run_worker_with_vpn.sh "$SERVICE"
      fi
    fi
  fi
  if [[ -n "$DEPLOY_NOTE" ]]; then echo "🔄 $DEPLOY_NOTE"; fi
fi

hc_ping /start

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

# On every exit: clean up, then report. Status 0 is not enough for success: if
# a state kept its old data (the rip cord in mapillary_pipeline), that is
# reported as a failure too - the incident of 2026-08-26 was such a partial run.
finish() {
  local rc=$?
  cleanup
  if (( rc != 0 )); then
    [[ -n "$HC_NOTE" ]] || HC_NOTE="Run aborted (exit $rc)."
    hc_ping /fail
  elif run_log_is_current && grep -q "Nicht aktualisiert" "$RUN_LOG"; then
    HC_NOTE="Finished, but some states kept their old data (see below)."
    hc_ping /fail
  else
    hc_ping ""
  fi
}
trap finish EXIT

# Container aufräumen
$DC down --remove-orphans

# ---------------------------
# 🗺️ VPN-Serverliste aktualisieren
# ---------------------------
# Die in gluetun eingebaute Serverliste veraltet: gluetun wählt zufällig auch
# Server, die es nicht mehr gibt, und braucht dann etliche Anläufe (je ~60 s
# TLS-Timeout), bis der Tunnel steht. Das Update schreibt eine aktuelle
# servers.json nach data/gluetun/, die docker-compose.vpn.yml einbindet.
# Scheitert es, geht es mit der zuletzt gespeicherten Liste weiter.
GLUETUN_IMAGE="$(grep -oE 'qmcgaw/gluetun:[^[:space:]]+' docker/docker-compose.vpn.yml | head -1)"
echo "🗺️  Aktualisiere VPN-Serverliste ($GLUETUN_IMAGE)..."
mkdir -p data/gluetun
if timeout 300 docker run --rm -v "$PWD/data/gluetun:/gluetun" \
     "$GLUETUN_IMAGE" update -enduser -providers nordvpn >/dev/null 2>&1; then
  echo "✅ Serverliste aktualisiert"
else
  echo "⚠️  Serverliste nicht aktualisiert — nutze die vorhandene"
fi

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
    echo "❌ Worker nach $WORKER_TIMEOUT abgebrochen (Hänger?) — kein Upload"
    HC_NOTE="Worker killed after $WORKER_TIMEOUT (hung?) - nothing uploaded."
  else
    echo "❌ Worker-Fehler (Exit $rc) — kein Upload"
    HC_NOTE="Worker failed (exit $rc) - nothing uploaded."
  fi
  exit 1
}

# ---------------------------
# ☁️ Schwere Outputs nach B2 archivieren (nicht in git)
# ---------------------------
# A failed or skipped upload (exit 1 or 3) does not stop the run - the data
# stays on disk - but the run counts as failed at the end: nothing was
# published, and data.vizsim.de keeps last week's state.
UPLOAD_OK=1
if ! "$(dirname "$0")/upload_outputs_to_b2.sh" "$SERVICE"; then
  UPLOAD_OK=0
  echo "⚠️  B2-Upload fehlgeschlagen oder übersprungen — nichts veröffentlicht."
fi

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
if [[ -e "$RUN_LOG" ]]; then
  grep -aE "Lauf beendet|Nicht aktualisiert|NICHT exportiert|VPN neu verbunden" "$RUN_LOG" | sed 's/^/   /'
else
  echo "   (keine Mitschrift unter $RUN_LOG)"
fi
if (( ! UPLOAD_OK )); then
  HC_NOTE="B2 upload failed or was skipped - nothing published this week."
  exit 1
fi
echo "🎉 Fertig!"
