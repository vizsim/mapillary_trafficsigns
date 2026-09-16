#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Lädt die schweren Output-Dateien eines Workers nach Backblaze B2 (Archiv),
# statt sie in git zu committen. Die Dateien bleiben lokal auf Platte.
#
# Aufruf:  upload_outputs_to_b2.sh <SERVICE>
#          DRY_RUN=1 upload_outputs_to_b2.sh <SERVICE>   # nur anzeigen
# Bucket:  vizsim-public-archive  (Endpoint s3.eu-central-003.backblazeb2.com)
#          öffentlich erreichbar unter https://data.vizsim.de/
#
# Defensive: fehlt b2-CLI oder Credentials, wird NUR gewarnt und übersprungen —
# ein Worker-Lauf darf daran NICHT scheitern.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

# b2 wird per `uv tool install b2` nach ~/.local/bin gelegt. Cron hat einen
# minimalen PATH (oft nur /usr/bin:/bin), in dem das fehlt → vorsorglich ergänzen,
# damit `command -v b2` auch im Cron-Kontext greift.
export PATH="$HOME/.local/bin:$PATH"

SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "❌ upload_outputs_to_b2: Service-Name fehlt"
  exit 2
fi

case "$SERVICE" in
  mapillary-ts_worker|mapillary-mk_worker) ;;
  *) echo "❌ Unbekannter Service '$SERVICE'"; exit 2 ;;
esac

# Credentials optional aus gitignored docker/.env ziehen (dort liegen schon die
# VPN-Creds). Erwartet: B2_ARCHIVE_KEY_ID / B2_ARCHIVE_KEY.
if [[ -f docker/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . docker/.env
  set +a
fi

# b2-CLI vorhanden?
if ! command -v b2 >/dev/null 2>&1; then
  echo "⚠️  b2-CLI nicht installiert ('uv tool install b2') — B2-Upload übersprungen."
  exit 0
fi

# Credentials vorhanden? Bewusst NICHT der gecachte unfallkarte-Key — der ist auf
# unfallkarte-data-v2 beschränkt. Nötig: eigener App-Key mit Schreibrecht auf
# vizsim-public-archive.
if [[ -z "${B2_ARCHIVE_KEY_ID:-}" || -z "${B2_ARCHIVE_KEY:-}" ]]; then
  echo "⚠️  B2_ARCHIVE_KEY_ID/B2_ARCHIVE_KEY nicht gesetzt — B2-Upload übersprungen."
  echo "    App-Key mit Schreibrecht auf vizsim-public-archive in docker/.env hinterlegen."
  exit 0
fi

# b2 v4 nutzt diese Env-Vars in-memory und fasst die gecachte Default-Auth
# (unfallkarte) NICHT an — so wird kein fremder Key überschrieben.
export B2_APPLICATION_KEY_ID="$B2_ARCHIVE_KEY_ID"
export B2_APPLICATION_KEY="$B2_ARCHIVE_KEY"

FAILED=0

# ---------------------------------------------------------------------------
# Ein Sync-Job.  sync_dir <SRC_DIR> <DEST> <INCLUDE_REGEX>…
#
# Prinzip: erst ALLES ausschließen (--exclude-regex ".*"), dann gezielt
# re-includen. Die Includes nennen die Dateien bewusst BEIM NAMEN statt per
# Endung (z. B. nicht `.*\.pmtiles$`): bei einem harten tippecanoe-Abbruch
# bleibt eine `*.tmp.pmtiles` liegen, und da --include Vorrang vor --exclude
# hat, würde ein Endungs-Muster diesen Müll mit veröffentlichen.
# → Neue Output-Dateien brauchen hier eine neue Zeile.
#
# Ohne --delete: alte Stände bleiben (Bucket ist ohnehin 'Keep all versions').
# ---------------------------------------------------------------------------
sync_dir() {
  local src="$1" dest="$2"
  shift 2

  if [[ ! -d "$src" ]]; then
    echo "⚠️  Quellverzeichnis '$src' fehlt — Job übersprungen."
    return 0
  fi

  local include_args=() re
  for re in "$@"; do
    include_args+=(--include-regex "$re")
  done

  local dry=()
  [[ -n "${DRY_RUN:-}" ]] && dry=(--dry-run)

  echo "☁️  Sync $src → $dest"
  # Ein fehlgeschlagener Job darf die anderen nicht verhindern (set -e umgehen).
  if b2 sync --no-progress "${dry[@]}" \
       --exclude-regex ".*" \
       "${include_args[@]}" \
       "$src" "$dest"; then
    return 0
  else
    echo "❌ Sync '$src' → '$dest' fehlgeschlagen."
    FAILED=1
    return 0
  fi
}

# ---------------------------------------------------------------------------
# Was wird wohin archiviert?
# ---------------------------------------------------------------------------
case "$SERVICE" in
  mapillary-ts_worker)
    # 1) Roh-/Zwischendaten: Parquets pro Bundesland + Lauf-Metadaten.
    sync_dir "output" \
      "b2://vizsim-public-archive/mapillary_trafficsigns/" \
      ".*mapillary_traffic-signs_.*\.parquet$" \
      ".*ml-ts_metadata\.json$" \
      ".*LICENSE\.txt$"

    # 2) Fertige Kampagnen-Outputs (Radinfrastruktur) — die Dateien, die auch
    #    2radinfra.de konsumiert. Stehen aktuell ZUSÄTZLICH noch in git;
    #    sobald die Konsumenten auf data.vizsim.de zeigen, können sie aus dem
    #    Repo fliegen (.gitignore + COMMIT_PATHS in run_worker_with_vpn.sh).
    sync_dir "use_cases/cycleway_complete_campaign/ts_output" \
      "b2://vizsim-public-archive/mapillary_trafficsigns/cycleway-campaign/" \
      ".*mapillary_trafficsigns_bicycle_latest\.pmtiles$" \
      ".*mapillary_trafficsigns_bicycle_latest\.geojson\.gz$" \
      ".*signs_by_month\.svg$" \
      ".*README\.md$"
    ;;

  mapillary-mk_worker)
    # 1) mk-Parquets (map-feature-points / Markierungen) — eigener Ziel-Ordner,
    #    bewusst getrennt von den traffic-signs, da anderer Datensatz.
    sync_dir "output" \
      "b2://vizsim-public-archive/mapillary_map-feature-points/" \
      ".*mapillary_map-feature-points_.*\.parquet$" \
      ".*ml-mf_metadata\.json$" \
      ".*LICENSE\.txt$"

    # 2) Fertige Kampagnen-Outputs (Radinfrastruktur-Markierungen) — analog zur
    #    ts-Kampagne. Stehen aktuell ZUSÄTZLICH noch in git; sobald die
    #    Konsumenten auf data.vizsim.de zeigen, können sie aus dem Repo fliegen
    #    (.gitignore + COMMIT_PATHS in run_worker_with_vpn.sh).
    sync_dir "use_cases/cycleway_complete_marking_campaign/mk_output" \
      "b2://vizsim-public-archive/mapillary_map-feature-points/cycleway-campaign/" \
      ".*mapillary_markings_bicycle_latest\.pmtiles$" \
      ".*mapillary_markings_bicycle_latest\.geojson\.gz$" \
      ".*markings_by_month\.svg$" \
      ".*README\.md$"
    ;;
esac

if [[ "$FAILED" -ne 0 ]]; then
  echo "❌ Mindestens ein B2-Sync ist fehlgeschlagen."
  exit 1
fi

echo "✅ B2-Upload fertig."
