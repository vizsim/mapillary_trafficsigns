# Plan: Notebooks → Python-Paket, Tests, uv

**Repo:** `vizsim/mapillary_trafficsigns`
**Branch:** `feature/docker-notebook`
**Stand:** 2026-09-02
**Status:** Schritte 0 und 1 erledigt, Schritt 2 zur Hälfte — alles auf Branch
`feature/pipeline-hardening`, Merge nach dem ts-Lauf vom 02.09.

> Vorlage ist das Schwesterrepo `mapillary_coverage`. Das ist denselben Weg
> bereits gegangen (0 Notebooks, 11 Module unter `src/`, uv + `pyproject.toml`,
> `config/*.toml`) und läuft laut User zuverlässig. Was dort **fehlt**, ist der
> Testteil — den würde ich hier nicht auch auslassen.

---

## Warum überhaupt

Nicht Eleganz, sondern ein konkreter Datenverlust. Am 26.08.2026 hat die
ts-Pipeline `DE-NW` mit 998 von 15.243 Tiles überschrieben — 1.391.990 Zeilen
runter auf 139.026, publiziert nach `data.vizsim.de`, und
`ml-ts_metadata.json` meldete trotzdem einen frischen Stand.

Die Ursache war nicht die Netzwerkstörung selbst, sondern **die Duplizierung**:
`2_get_mapillary_traffic_signs.ipynb` und `2b_get_mapillary_map_feature_points.ipynb`
enthielten dieselbe Tile-Logik zweimal. Der Timeout-/Retry-Fix `6a6dd81` wurde
nur in `2b` eingebaut. Dass `2` dieselbe Stelle hat, ist fünf Wochen lang
niemandem aufgefallen — in einem Notebook-Diff sieht man so etwas nicht.

Dazu kommt: jeder Worker-Lauf committet die Notebooks **mit Outputs**. Ein Lauf
mit vielen Tile-Fehlern bläht die Datei von ~26 KB auf 17,5 MB
(132.603 identische Log-Zeilen), jede Woche als neuer Blob. Siehe
`git-history-rewrite` — das Repo musste deshalb schon einmal von 4,3 GB auf
58 MB umgeschrieben werden.

---

## Schritte

| # | Thema | Aufwand | Status |
|---|---|---|---|
| 0 | Gemeinsames Tile-Modul `mapillary_tiles.py` | klein | ✅ **erledigt** (2026-08-31) |
| 1 | Tests für die Export-Entscheidung | klein | ✅ **erledigt** (2026-09-02, 21 Tests, `venv/bin/pytest`) |
| 2 | Paketstruktur `src/mapillary_trafficsigns/` | mittel | 🟡 **halb** — Module im Repo-Root, Notebooks auf 3 Zellen; `src/`-Layout offen |
| 3 | CLI + Config statt Notebook-Konstanten | mittel | offen |
| 4 | uv statt `requirements.txt` | klein | offen |
| 5 | Notebook-Outputs aus git | klein | offen |
| 6 | CI | klein | offen |

### Zusätzlich erledigt am 2026-09-02 (Branch `feature/pipeline-hardening`)

Ergebnis einer Durchsicht des ganzen Repos, nicht nur der Download-Notebooks:

- **Nachlauf** (`fetch_tiles_with_retry`): endgültig gescheiterte Tiles werden nach 5 min
  Pause noch einmal geholt, bevor die Reißleine ein ganzes Bundesland kippt. Ohne das
  hätte ein Land mit 3 % Lücken komplett gewartet, obwohl 97 % da waren.
- **Abbruch nach Fehlerserie** (`fetch_tiles`, `abort_after=30`): trifft ein Fehlerzustand
  jede Tile (etwa HTML statt MVT), wird nach 30 Fehlern in Folge abgebrochen statt jede
  Tile einzeln durchzuwiederholen; der Rest gilt als „nicht versucht", die Reißleine greift.
- **VPN neu verbinden** (`reconnect_vpn`, 2026-09-03): wurde wegen ungültiger Antworten
  abgebrochen, verbindet der Worker den Tunnel vor dem Nachlauf über die gluetun-Steuer-API
  neu. Braucht `GLUETUN_API_KEY` in `docker/.env` (Vorlage in `.env.example`); ohne Key ein
  No-op.
- **Live-Mitschrift** (`RunLog`): `logs/{ts,mk}_run_latest.log` im Bind-Mount, während des
  Laufs lesbar. nbconvert schreibt Zell-Ausgaben erst am Ende — deshalb war der mk-Lauf
  vom 27.08. nicht rekonstruierbar.
- **Nur ein Worker gleichzeitig** (`flock` in `run_worker_with_vpn.sh`): `docker compose down`
  ist projektweit; ein mk-Start während eines laufenden ts-Laufs hätte ihn gekillt.
  Dazu `timeout 16h`, damit ein Hänger nicht über das Lock alle Folgeläufe blockiert.
- **gluetun-Logs** werden vor dem `down` nach `logs/gluetun-<service>.log` gesichert.
- **Ein Runner statt zwei** (`scripts/run_mapillary_notebooks.sh ts|mk`): die beiden
  Skripte waren bis auf drei Pfade byteidentisch, und das Argument aus
  `docker-compose.yml` hat keines von beiden je gelesen.
- **`git add`-Fehler** (index.lock, Rechte) brechen den Auto-Commit ab, statt als
  „kein Treffer" durchzugehen.
- **Secrets nicht mehr im Image** (`.dockerignore`: `config.json`, `config.py`,
  `config_mapillary_privat.json`) — zur Laufzeit kommt alles vom Bind-Mount.
- **Downstream `generateOutput` (ts)**: Vollständigkeits-Guard (16 von 16 Parquets, sonst
  Abbruch statt Teil-Publish — `all([])` war `True`), spaltenselektives Laden mit frühem
  Filter wie im mk-Notebook (296.970 Zeilen in 9 s statt alle 16 Länder komplett im
  6g-Container), `delta_days_seen` vektorisiert statt `strptime` pro Zeile.
- **id-Regressionscheck** (ts + mk) prüft ein 4-MB-Fenster per Regex statt die ganze
  GeoJSON am RAM-Peak ein zweites Mal zu parsen.
- **Secrets-Pfad** im ts-`1_merge`-Notebook auf `../utils/` wie im mk-Zwilling — sonst
  existieren zwei Kopien der Zugangsdaten.

### Bewusst NICHT angefasst (aus der Durchsicht, für später)

- `upload_outputs_to_b2.sh` warnt nur, wenn b2/Creds fehlen, der Commit läuft trotzdem
  und die README zeigt B2-Links. Verhalten ist so gewollt („defensiv") — aber ein
  Hinweis in der Commit-Message, wenn nichts hochgeladen wurde, wäre ehrlich.
- `*.pmtiles` / `*_latest.geojson.gz` werden weiter committet (~34 MB/Woche) — siehe
  Git-History-Rewrite; erst wenn die Konsumenten auf `data.vizsim.de` zeigen.
- Die 100-Zeilen-Funktion `gzgjson_to_pmtiles_dual_layer` liegt in beiden
  pmtiles-Notebooks identisch. Ein gemeinsames Modul bräuchte `sys.path`-Anpassung in
  den use_case-Notebooks (nbconvert setzt cwd auf das Notebook-Verzeichnis).
- `docs/` steht in `.gitignore`, zwei Dateien sind trotzdem getrackt.
- `--abort-on-container-exit` reißt den Lauf, sobald *irgendein* Container im
  Projekt-Netz endet (so ist am 31.08. der coverage-Lauf gestorben). Mit dem Lock ist
  das Risiko klein; eine Umstellung auf `up -d` + `wait` wäre sauberer.

---

### Schritt 0 — gemeinsames Tile-Modul ✅

Erledigt am 2026-08-31. `mapillary_tiles.py` im Repo-Root, importiert von beiden
Notebooks. Enthält `TileError`, `get_session`, `fetch_tile_bytes`, `load_tile`,
`tile_features_to_gdf`, `TileBatch`, `fetch_tiles`. Die Pipelines unterscheiden
sich nur noch über `COVERAGE_TRAFFIC_SIGNS` / `COVERAGE_MAP_FEATURES`.

Der Import funktioniert, weil `docker-compose.yml` `working_dir: /app` setzt und
das Repo per Bind-Mount komplett unter `/app` liegt.

**Damit ist der eigentliche Auslöser weg.** Die folgenden Schritte sind
Verbesserungen, keine Reparaturen — entsprechend ohne Zeitdruck.

---

### Schritt 1 — Tests für die Export-Entscheidung

Der höchste Ertrag pro Aufwand, und der Teil, den `mapillary_coverage`
ausgelassen hat. Die Logik, die den Schaden verursacht hat, ist rein und ohne
Netz testbar:

```python
def test_kein_export_wenn_zu_viele_tiles_fehlen(tmp_path):
    # 100 Tiles, 60 scheitern -> weder Parquet noch Metadaten anfassen
def test_export_wenn_alle_tiles_da(tmp_path):
def test_leeres_tile_ist_kein_fehler():
    # 200 mit leerem Body -> empty, nicht failed
def test_html_body_wird_als_fehler_erkannt():
    # 200 + text/html -> TileError, nicht MVT-Parsefehler
def test_parse_fehler_wird_wiederholt():
    # erster Versuch Müll, zweiter sauber -> Erfolg
def test_id_bleibt_exakt_ueber_2_hoch_53():
    # Regression zu ab5e8b1 (Float-Rundung von Mapillary-IDs)
```

**Erledigt 2026-09-02:** `tests/test_mapillary_tiles.py` (13) und
`tests/test_mapillary_pipeline.py` (8), ohne Netz — Session und Parser werden
per `monkeypatch` ersetzt, keine Zusatzabhängigkeit außer `pytest`
(`requirements-dev.txt`, `pytest.ini`). Der erste Pipeline-Test ist der
NW-Fall vom 26.08.: 100 Tiles, 60 scheitern → weder Parquet noch Metadaten
angefasst. Gegen den alten Code wäre er rot. Laufzeit ~1,5 s.

Noch nicht dabei: ein echter Ende-zu-Ende-Test des Notebooks per nbconvert
(braucht das Docker-Image); der Import im Worker-Image wurde am 31.08. manuell
verifiziert.

---

### Schritt 2 — Paketstruktur

Nach dem Vorbild von `mapillary_coverage`:

```text
src/mapillary_trafficsigns/
├── __init__.py
├── cli.py            # Einstiegspunkt, ersetzt die Notebook-Ausführung
├── tiles.py          # aus mapillary_tiles.py
├── export.py         # export_geodata + Metadaten
├── bundeslaender.py  # Tile-Cache laden
├── runner.py         # Schleife über Bundesländer, Lauf-Bilanz
└── settings.py       # config/*.toml einlesen
tests/
```

Die Notebooks bleiben zunächst als dünne Schaufenster (drei Zellen: importieren,
aufrufen, Ergebnis anschauen) oder verschwinden ganz. Wichtig: `use_cases/`
enthält weitere Notebooks, die von den Outputs abhängen — die bleiben vorerst
unangetastet.

**Achtung Reihenfolge:** `scripts/run_worker_with_vpn.sh` staged die Notebook-
Pfade explizit pro Worker (`COMMIT_PATHS`). Fällt ein Notebook weg, muss die
Liste mit.

---

### Schritt 3 — CLI + Config

`config.json` (nur Token) und die im Notebook verstreuten Konstanten
(`max_workers=3`, `max_fail_ratio=0.02`, Pfade) nach `config/default.toml` +
`config/local.toml`, wie in coverage. Token zusätzlich über
`MAPILLARY_ACCESS_TOKEN` aus dem Env.

Ziel: `mapillary-trafficsigns run --pipeline ts --bundesland DE-NW` — damit ist
ein Nachlauf für einzelne Länder möglich, statt alle 158.829 Tiles neu zu holen.
Zusammen mit den Fehlerlisten aus `prep/tile_cache/failed/` wäre das der Weg,
Lücken gezielt zu schließen.

---

### Schritt 4 — uv

**Kein conda im Spiel** — `docker/Dockerfile.worker` baut mit
`pip install -r requirements.txt`, und alle 81 Zeilen sind bereits gepinnt. Der
Gewinn ist deshalb kleiner als es zunächst klingt: transitive Locks und
Build-Tempo, nicht Reproduzierbarkeit.

`requirements.txt` → `pyproject.toml` + `uv.lock`, Dockerfile analog zu coverage:

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /uvx /bin/
ENV UV_LINK_MODE=copy
COPY . .
RUN uv sync --frozen
```

Zu beachten: das ts-Image baut zusätzlich **tippecanoe** aus dem Quelltext. Der
Teil bleibt, wie er ist.

---

### Schritt 5 — Notebook-Outputs aus git

Solange Notebooks committet werden, gehört ein `nbstripout`-Hook oder ein
`--ClearOutputPreprocessor` vor den Auto-Commit in
`scripts/run_worker_with_vpn.sh`. Sonst wächst das Repo weiter über die
Lauf-Logs.

Der Sammelbericht aus Schritt 0 entschärft das bereits an der Wurzel (statt
132.603 Zeilen jetzt eine Handvoll), aber die Absicherung kostet nichts.

---

### Schritt 6 — CI

`mapillary_coverage` hat kein `.github/workflows/`. Ein Minimal-Workflow
(`pytest` + `ruff` auf Push) macht Schritt 1 erst wirksam — sonst laufen die
Tests nur, wenn jemand daran denkt.

---

## Was NICHT Teil des Plans ist

- **`mapillary_coverage` anfassen.** Eigenes Repo, läuft. (Randnotiz für später:
  dort steht in `mapillary.py:404` `if bundesland_geodataframes: export_geodata(...)`
  — auch nach zwei Retry-Runden mit verbleibenden Fehlern wird exportiert. Die
  Retry-Runden machen den NW-Fall unwahrscheinlicher, nicht unmöglich.)
- **Streaming-Umbau** (ParquetWriter statt sammeln+concat). Eigener Plan unter
  `~/.claude/plans/jaunty-wibbling-hopper.md`, nur nötig, falls der 8G-Swap nicht
  reicht.

---

## Geklärt am 2026-09-02: woher die Antworten ohne MVT-Inhalt kamen

Über den bisherigen VPN-Exit (Deutschland) kam ab Ende August für jede Tile
HTTP 200 mit einer HTML-Seite statt eines MVT zurück — deshalb die 132.603
Parse-Fehler am 26.08. und das stundenlange Kriechen am 02.09. (jede Tile 4
Versuche mit Backoff). Von einem anderen Anschluss laden dieselben Tiles
einwandfrei.

Konsequenzen: Exit-Land auf Niederlande umgestellt (Berlin wäre die
naheliegende Alternative gewesen, ist aber von Hetzner aus nicht erreichbar —
Routing, 100 % Paketverlust nach 194.233.96.x), und `fetch_tiles` bricht nach
30 Fehlern in Folge ab, statt jede Tile einzeln durchzuwiederholen. Damit
scheitert ein solcher Lauf in Minuten, die Reißleine hält den alten Stand, und
die Mitschrift zeigt den Body.

Ebenfalls offen: warum der mk-Lauf vom 27.08. nur 7 von 16 Ländern erneuert hat.
Aus `logs/cron-mk.log` nicht rekonstruierbar, weil die Notebook-Ausgabe dort
nicht landet (`Starte Verarbeitung` findet null Treffer). Das Logging der
mk-Pipeline gehört mit auf die Liste.
