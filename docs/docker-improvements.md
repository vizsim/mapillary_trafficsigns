# Docker-Infrastruktur: Änderungen & offene TODOs

## Session 2026-03-20 — Was wurde gemacht und warum

### 1. `.dockerignore` ergänzt

**Dateien:** `.dockerignore`

**Problem:** `venv/`, `schrott/`, `logs/`, `*.gpkg`, `*.fgb`, `*.log` fehlten im `.dockerignore`. Ohne das werden diese Verzeichnisse und Dateien beim `docker build` in den Build-Kontext kopiert, was Builds unnötig verlangsamt und Images aufbläht.

**Fix:** Fehlende Einträge ergänzt. Das Image selbst ist zur Laufzeit ohnehin weitgehend irrelevant, da der Container das Repo per Volume-Mount (`..:/app`) einbindet.

---

### 2. Gluetun-Healthcheck eingebaut

**Dateien:** `docker/docker-compose.vpn.yml`, `scripts/run_worker_with_vpn.sh`

**Problem:** Der bisherige VPN-Readiness-Check wartete per `grep` auf bestimmte Log-Strings von Gluetun:
```bash
until docker logs gluetun 2>&1 | grep -q "Initialization Sequence Completed"; do sleep 2; done
until docker logs gluetun 2>&1 | grep -qi "dns.*ready"; do sleep 2; done
```
Das ist fragil: Log-Texte können sich zwischen Gluetun-Versionen ändern, Race-Conditions sind möglich, und der zweite `grep` auf `dns.*ready` matchte ohnehin nicht zuverlässig.

**Fix:**
- Gluetun bekommt einen echten `healthcheck` via `/gluetun-entrypoint healthcheck` (Gluetun-interne Binary, prüft den VPN-Status über `http://localhost:9999/`)
- `retries: 30` × `interval: 10s` = 300s Puffer, passend zum bisherigen 5-Minuten-Timeout
- Der Wait-Loop im Script nutzt jetzt `docker inspect --format='{{.State.Health.Status}}'` statt Log-Parsing

---

### 3. `--abort-on-container-exit --exit-code-from` hinzugefügt

**Datei:** `scripts/run_worker_with_vpn.sh`

**Problem (Hauptfehler beim letzten Lauf):** Der Worker-Aufruf war:
```bash
docker-compose up --build "$SERVICE"
```
Da Gluetun bereits separat gestartet war und mit `restart: unless-stopped` läuft, kehrt `docker-compose up` nicht sauber zurück wenn der Worker fertig ist. Der Auto-Commit-Block wurde dadurch nie erreicht. Der Worker lief erfolgreich, aber Commit und Push fanden nicht statt.

**Fix:**
```bash
docker-compose up --build --abort-on-container-exit --exit-code-from "$SERVICE" "$SERVICE"
```
Compose wartet jetzt bis der Worker-Container beendet ist, gibt dessen Exit-Code zurück, und das Script läuft danach weiter.

---

### 4. Git-Change-Detection robuster gemacht

**Datei:** `scripts/run_worker_with_vpn.sh`

**Problem:** Der alte Check prüfte Änderungen *vor* dem Stagen:
```bash
if git diff --quiet && git diff --cached --quiet; then ...
```
Untracked neue Dateien (z.B. neue Output-Dateien) werden von `git diff` nicht erkannt — sie wären im Diff nicht sichtbar gewesen.

**Fix:** Erst stagen, dann prüfen:
```bash
git add -A
if git diff --cached --quiet; then ... # nichts zu committen
fi
```

---

### 5. Commit-Message zeigt jetzt den Worker-Namen

**Datei:** `scripts/run_worker_with_vpn.sh`

**Vorher:** `Auto-update: outputs, notebooks, metadata (2026-03-20T...)`

**Nachher:** `Auto-update [mapillary-ts_worker]: outputs, notebooks, metadata (2026-03-20T...)`

---

### 6. Gluetun-Cleanup per `trap`

**Datei:** `scripts/run_worker_with_vpn.sh`

**Problem:** Gluetun hat `restart: unless-stopped` und lief nach dem Worker-Lauf dauerhaft weiter, bis zum nächsten manuellen `down` oder Cron-Lauf.

**Fix:** `trap` sorgt dafür, dass `docker-compose down --remove-orphans` bei jedem Exit des Scripts ausgeführt wird — egal ob Erfolg, Fehler oder SIGTERM:
```bash
trap '$DC down --remove-orphans 2>/dev/null || true' EXIT
```

---

### 7. Branch dynamisch statt hardcodiert

**Datei:** `scripts/run_worker_with_vpn.sh`

**Vorher:** `BRANCH="feature/docker-notebook"` — würde auch dann auf diesen Branch pushen wenn das Script auf einem anderen Branch läuft.

**Nachher:** `BRANCH="$(git rev-parse --abbrev-ref HEAD)"` — pusht immer auf den aktuell ausgecheckten Branch.

---

## Offene TODOs

### TODO-1: `docker-compose` → `docker compose`

**Datei:** `scripts/run_worker_with_vpn.sh`, Zeile 18

Das alte `docker-compose` (v1, standalone Python-Binary) ist deprecated und auf neueren Systemen nicht mehr installiert. Das moderne Plugin wird als `docker compose` (Leerzeichen) aufgerufen.

```bash
# aktuell:
DC="docker-compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"
# neu:
DC="docker compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"
```

**Priorität:** mittel — funktioniert solange `docker-compose` v1 installiert ist, aber könnte auf neuen Servern brechen.

---

### TODO-2: `version: "3.9"` aus Compose-Files entfernen

**Dateien:** `docker/docker-compose.yml`, `docker/docker-compose.vpn.yml`

In Docker Compose v2 ist das `version:`-Feld obsolet und wird ignoriert. Es erzeugt eine Deprecation-Warnung in den Logs.

**Fix:** Einfach die erste Zeile in beiden Dateien entfernen.

**Priorität:** niedrig — rein kosmetisch, kein funktionaler Effekt.

---

### TODO-3: Unused Argumente in `docker-compose.yml`

**Datei:** `docker/docker-compose.yml`

Die Worker-Commands übergeben ein Argument das nie genutzt wird:
```yaml
command: ["bash", "/app/scripts/run_mapillary-ts_notebooks.sh", "ts"]
```
Das `"ts"` / `"mk"` wird von den Scripts nicht ausgewertet (`$1` wird nie gelesen). Entweder entfernen oder in den Scripts tatsächlich nutzen.

**Priorität:** niedrig — kein Bug, nur unaufgeräumt.

---

### TODO-4: Notebook-Execution-Timeout setzen

**Dateien:** `scripts/run_mapillary-ts_notebooks.sh`, `scripts/run_mapillary-mk_notebooks.sh`

`jupyter nbconvert --execute` hat standardmäßig kein Timeout. Ein hängender API-Call (z.B. Mapillary-Rate-Limit, Netzwerkproblem) würde den Cron-Job ewig blockieren.

**Fix:** `--ExecutePreprocessor.timeout=3600` (oder einen anderen sinnvollen Wert) zu allen `nbconvert`-Aufrufen hinzufügen:
```bash
jupyter nbconvert \
  --to notebook \
  --inplace \
  --execute \
  --ExecutePreprocessor.timeout=3600 \
  notebook.ipynb
```

**Priorität:** mittel — im Fehlerfall hängt der Cron-Job sonst dauerhaft.
