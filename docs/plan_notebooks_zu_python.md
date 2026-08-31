# Plan: Notebooks → Python-Paket, Tests, uv

**Repo:** `vizsim/mapillary_trafficsigns`
**Branch:** `feature/docker-notebook`
**Stand:** 2026-08-31
**Status:** Plan, nicht begonnen. Schritt 0 (gemeinsames Tile-Modul) ist erledigt.

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
| 1 | Tests für die Export-Entscheidung | klein | offen |
| 2 | Paketstruktur `src/mapillary_trafficsigns/` | mittel | offen |
| 3 | CLI + Config statt Notebook-Konstanten | mittel | offen |
| 4 | uv statt `requirements.txt` | klein | offen |
| 5 | Notebook-Outputs aus git | klein | offen |
| 6 | CI | klein | offen |

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

`pytest` + `responses` oder `requests-mock`, keine echten Requests. Läuft in
Sekunden.

**Akzeptanzkriterium:** `pytest` grün, und der NW-Fall vom 26.08. ist als Test
formuliert, der gegen den alten Code rot wäre.

---

### Schritt 2 — Paketstruktur

Nach dem Vorbild von `mapillary_coverage`:

```
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

## Offene Frage, die vor Schritt 2 beantwortet sein sollte

Warum bekommt der Server überhaupt Antworten ohne MVT-Inhalt? Verdacht: der
NordVPN-Exit wird von Mapillary geblockt oder gedrosselt. Von einem normalen
Anschluss laden dieselben Tiles einwandfrei.

Der Sammelbericht zeigt beim nächsten Lauf (Mi 15:00 ts, Do 01:00 mk) den echten
Body. **Erst danach urteilen** — sonst wird umgebaut und die Ursache steht
danach immer noch offen.

Ebenfalls offen: warum der mk-Lauf vom 27.08. nur 7 von 16 Ländern erneuert hat.
Aus `logs/cron-mk.log` nicht rekonstruierbar, weil die Notebook-Ausgabe dort
nicht landet (`Starte Verarbeitung` findet null Treffer). Das Logging der
mk-Pipeline gehört mit auf die Liste.
