#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Lädt die schweren Output-Dateien eines Workers nach Backblaze B2 (Archiv),
# statt sie in git zu committen. Die Dateien bleiben lokal auf Platte.
#
# Aufruf:  upload_outputs_to_b2.sh <SERVICE>
# Bucket:  vizsim-public-archive  (Endpoint s3.eu-central-003.backblazeb2.com)
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

# Credentials optional aus gitignored docker/.env ziehen (dort liegen schon die
# VPN-Creds). Erwartet: B2_ARCHIVE_KEY_ID / B2_ARCHIVE_KEY.
if [[ -f docker/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . docker/.env
  set +a
fi

# Was wird wohin archiviert?
case "$SERVICE" in
  mapillary-ts_worker)
    SRC_DIR="output"
    INCLUDE_REGEXES=(
      ".*mapillary_traffic-signs_.*\.parquet$"
      ".*ml-ts_metadata\.json$"
    )
    DEST="b2://vizsim-public-archive/mapillary_trafficsigns/"
    ;;
  mapillary-mk_worker)
    # mk-Parquets (map-feature-points / Markierungen) — eigener Ziel-Ordner,
    # bewusst getrennt von den traffic-signs, da anderer Datensatz.
    SRC_DIR="output"
    INCLUDE_REGEXES=(
      ".*mapillary_map-feature-points_.*\.parquet$"
      ".*ml-mf_metadata\.json$"
    )
    DEST="b2://vizsim-public-archive/mapillary_map-feature-points/"
    ;;
  *)
    echo "❌ Unbekannter Service '$SERVICE'"
    exit 2
    ;;
esac

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

echo "☁️  Sync $SERVICE-Outputs → $DEST"
# Alles ausschließen, dann gezielt re-includen (Parquets + Metadata-JSON).
include_args=()
for re in "${INCLUDE_REGEXES[@]}"; do
  include_args+=(--include-regex "$re")
done
# Ohne --delete: alte Stände bleiben (Bucket ist ohnehin 'Keep all versions').
b2 sync --no-progress \
  --exclude-regex ".*" \
  "${include_args[@]}" \
  "$SRC_DIR" "$DEST"

echo "✅ B2-Upload fertig."
