# TODO

**Stand:** 2026-10-17

Ersetzt `plan_notebooks_zu_python.md`, `docker-improvements.md` und
`worker_mix_fehleranalyse_und_todos.md`. Was dort noch offen war, steht hier;
was erledigt oder hinfällig ist, listet der letzte Abschnitt. Die beiden
getrackten alten Dokumente liegen in der git-History (letzter Stand `f4b2c49`),
`worker_mix_…` war nie getrackt und ist seit dem 17.10. gelöscht.

**Aufwand** ist grobe Arbeitszeit. **Nutzen:** hoch / mittel / gering.
**Prio:** P1 = bald · P2 = als Nächstes · P3 = bei Gelegenheit · optional = nur bei Bedarf ·
später = bewusst zurückgestellt, bis die übrigen Kampagnen umgestellt werden (Entscheidung 17.10.).

## Übersicht

| # | Aufgabe | Aufwand | Nutzen | Prio |
|--:|:--------|:--------|:-------|:-----|
| 1 | Mapillary-Token rotieren, `config.py` löschen | 5 min Rest | hoch | P1, fast ✅ |
| 2 | Bildauswahl in tempo30 korrigieren | 1–2 h | hoch | später |
| 3 | Fehlschläge melden | 1 h | hoch | P1 |
| 4 | Kopfzellen der `radinfra_1_export` korrigieren | 15 min | mittel | ✅ 17.10. |
| 5 | Deploy-Weg festlegen | 30 min | mittel | P2 |
| 6 | Kampagnen-Inventur | 30 min | mittel | P2 |
| 7 | Alte Notebooks entfernen (ab 08.10.) | 1 h | mittel | ✅ 17.10. |
| 8 | tippecanoe-Funktion ins Modul | 1–2 h | mittel | später |
| 9 | Eine Python-Umgebung (uv) | ½ Tag | mittel | P2 |
| 10 | CI | 1 h | hoch | P2 |
| 11 | Notebook-Outputs aus git | 30 min | mittel | P2 |
| 12 | Generisches `campaign.py` | 1 Tag + ½ Tag je Kampagne | mittel | später |
| 13 | CLI statt Root-Notebooks | ½ Tag Rest | gering | P3, Kern ✅ 17.10. |
| 14 | `src/`-Paketstruktur | ½ Tag | gering | P3 |
| 15 | `docs/betrieb.md` | 1 h | mittel | P3 |
| 16 | Token-Quellen vereinheitlichen | 30 min | gering | P3 |
| 17 | `.gitignore` aufräumen | 20 min | gering | P3 |
| 18 | mk-README angleichen | 1 h | gering | P3 |
| 19 | Zweiter History-Rewrite | ½ Tag | gering | optional |
| 20 | Streaming-Export | 1 Tag | gering | optional |
| 21 | Ende-zu-Ende-Test im Image | ½ Tag | gering | optional |
| 22 | Commit-Sperre für Tokens | 30 min | mittel | optional |

---

## P1 — bald

### 1. Mapillary-Token rotieren, `config.py` löschen

**Aufwand:** 5 min Rest · **Nutzen:** hoch · **Prio:** P1

Der bis Oktober 2026 genutzte Token steht in der öffentlichen History. Er stand
nie im Code, sondern in Fehlermeldungen: Die Tile-API nimmt den Token nur als
URL-Parameter, gescheiterte Abrufe druckten die URL samt Token aus, und die
Notebooks `2_`/`2b_` wurden mit diesen Ausgaben committet (09.2025–04.2026).
Wer ihn findet, verbraucht das Kontingent dieses Tokens mit. Rotieren genügt,
die History muss dafür nicht neu geschrieben werden.

- ✅ 17.10.: neuer Token in `config.json` und
  `use_cases/utils/config_mapillary_privat.json`, lokal und auf dem Server,
  gegen Kachel- und Graph-API getestet.
- ✅ 17.10.: `mapillary_tiles.py` schwärzt den Token in allen Meldungen
  (Ausnahmen, Fehler-Bodies, Wiederholungs-Warnungen von urllib3).
- ✅ 17.10.: `config.py` gelöscht. Sie wurde in diesem Repo nie importiert,
  stammte aus dem coverage-Repo und hielt den alten Token im Klartext.
- **Offen:** den alten Token im Mapillary-Dashboard löschen.

### 3. Fehlschläge melden

**Aufwand:** 1 h · **Nutzen:** hoch · **Prio:** P1

Ein gescheiterter Lauf steht nur in `logs/cron-*.log`; auf dem Server ist
kein Mailversand eingerichtet. Schlimmer: fehlen b2-CLI oder Zugangsdaten,
endet `upload_outputs_to_b2.sh` mit Exit 0 — und seit B2 der einzige
Veröffentlichungsweg ist, heißt das: nichts publiziert, niemand merkt es.

- Am Ende von `run_worker_with_vpn.sh` Erfolg oder Fehler an einen Dienst
  melden (ntfy, healthchecks.io). healthchecks.io meldet zusätzlich einen
  Lauf, der gar nicht erst startet.
- Den übersprungenen Upload als Fehler werten, nicht als Warnung.

---

## P2 — als Nächstes

### 5. Deploy-Weg festlegen

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** P2

Ein Push nach `main` erreicht den Server nicht von selbst:
`run_worker_with_vpn.sh` zieht nicht. Vergisst man das `git pull --ff-only`
auf dem Server, läuft eine Woche lang der alte Stand. (Früher Task 12 in
`worker_mix_…`, damals offen gelassen.)

Entscheiden:
- **Auto-Pull** am Anfang des Laufs, mit Abbruch bei Nicht-Fast-Forward. Jeder
  Push nach `main` geht dann am nächsten Mittwoch live.
- **Manuell bleiben**, dann gehört der Schritt in #15.

### 6. Kampagnen-Inventur

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** P2

Welche Kampagnen leben noch? rad_frei und pedestrian_crossing_marking stehen
in der README als „work in progress", access_restrictions steht gar nicht
drin, `analysis/analize_osm_ts.ipynb` ist ein Einzelstück. Tote Kampagnen
löschen (git behält sie), lebende in die README. Legt fest, wie viel Arbeit
#2 und #12 wirklich sind.

Stand der Challenges laut MapRoulette am 17.10.:

| Challenge | Kampagne | Status | Daten vom |
| --- | --- | --- | --- |
| 52916 | Radinfra, Verkehrszeichen | aktiv | 14.09.2026 |
| 53882 | Radinfra, Markierungen | aktiv | 14.09.2026 |
| 52985 | Tempo 30 an Schulen | aktiv | 17.08.2025 |
| 53589 | Fußgängerüberwege, Verkehrszeichen | **abgeschlossen** | 14.11.2025 |
| — | Fußgängerüberwege, Markierungen; rad_frei; access_restrictions | keine Challenge | — |

### 9. Eine Python-Umgebung (uv)

**Aufwand:** ½ Tag · **Nutzen:** mittel · **Prio:** P2

Heute gibt es zwei: `venv/` mit `requirements.txt` (Server, `tests/`) und
`use_cases/.venv` mit `pyproject.toml`/`uv.lock` (Kampagnen). Ein Test
existiert nur, um beide synchron zu halten, und `pytest.ini` sammelt nur
`tests/` — ein nacktes `pytest` im Root lässt 71 von 115 Tests aus.

- Eine `pyproject.toml` + `uv.lock` im Root, `testpaths` auf beide Ordner.
- Dockerfile wie in coverage (`uv sync --frozen`); der tippecanoe-Build
  bleibt, wie er ist.
- Danach kann der Sync-Test weg.

### 10. CI

**Aufwand:** 1 h (nach #9) · **Nutzen:** hoch · **Prio:** P2

Die 115 Tests laufen nur, wenn jemand daran denkt; der einzige
Integrationstest ist der Mittwochslauf, und ein Fehlschlag kostet eine Woche.
Eine GitHub Action mit `pytest` bei jedem Push nach `main`.

### 11. Notebook-Outputs aus git

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** P2

Seit dem 02.09. committet der Server nichts mehr, die ausgeführten Kopien
landen in `logs/executed/`. Offen ist die Handarbeit: das Produktions-Notebook
`radinfra_2_pmtiles` trägt noch 32 (ts) bzw. 14 (mk) Outputs, die
Kampagnen-Notebooks 250 KB bis 2 MB. Notebook-Outputs haben die History im
Juli auf 4,3 GB gebracht — und über Fehlermeldungen den Mapillary-Token
veröffentlicht (#1).

- `nbstripout` als git-Filter einrichten — die lokale Arbeitskopie behält ihre
  Outputs, committet wird ohne.
- Bestehende Outputs einmal entfernen.

---

## P3 — bei Gelegenheit

### 13. CLI statt Root-Notebooks

**Aufwand:** ½ Tag Rest · **Nutzen:** gering · **Prio:** P3

- ✅ 17.10.: Der Runner ruft `python3 -m mapillary_pipeline ts|mk` statt der
  Notebooks `2_`/`2b_`, die gelöscht sind. Jupyter ist damit aus dem
  Kachelabruf raus, dessen Ausgabe steht live im Cron-Log, und ein Nachlauf
  für einzelne Länder geht mit `--bundesland DE-NW`. Probeläufe
  (`--limit-tiles`) verweigern `output/` als Ziel.
- **Offen:** Konstanten (`max_workers`, `max_fail_ratio`, Pfade) nach
  `config/*.toml` wie in coverage. Lohnt erst, wenn sie sich tatsächlich ändern.
- `0_prepare_tiles.ipynb` bleibt im Root: einmalige Vorbereitung des
  Kachel-Caches, von nichts aufgerufen.

### 14. `src/`-Paketstruktur

**Aufwand:** ½ Tag · **Nutzen:** gering · **Prio:** P3

`mapillary_tiles.py` und `mapillary_pipeline.py` im Root, `cw_campaign.py` in
`use_cases/`, jeweils per `sys.path` gefunden. Ein Paket unter
`src/mapillary_trafficsigns/` macht die Pfad-Tricks überflüssig. Nur zusammen
mit #9 und #13 sinnvoll.

### 15. `docs/betrieb.md`

**Aufwand:** 1 h · **Nutzen:** mittel · **Prio:** P3

Das Betriebswissen steht verstreut in Commit-Messages: Cron-Zeiten (ts Mi
15:00 UTC, mk Do 01:00 UTC), Deploy (#5), Wiederherstellen aus B2, auf dem
Server `checkout -B main origin/main` statt Branch-Wechsel (ein Wechsel hat
am 16.09. die ignorierten Lauf-Outputs gelöscht), Aussetzen und
Wiederherstellen des Crontabs, `max_file_age_days` und manuelle Läufe. Dazu,
wer die veröffentlichten Dateien liest: radinfra.de, und unfallkarte bindet die
PMTiles als „external"-Layer über ihre feste URL auf data.vizsim.de ein —
Dateinamen und Pfade dort dürfen sich nicht beiläufig ändern. Eine Seite dafür.

### 16. Token-Quellen vereinheitlichen

**Aufwand:** 30 min · **Nutzen:** gering · **Prio:** P3

Es bleiben zwei Dateien: `config.json` (Pipeline, rad_frei, analysis) und
`use_cases/utils/config_mapillary_privat.json` (Kampagnen, dazu der
MapRoulette-Key). Die alten Kampagnen-Notebooks lesen die zweite direkt ein,
deshalb passt das zu #12. Beide Loader lesen `MAPILLARY_ACCESS_TOKEN` schon aus der
Umgebung. Auf eine Datei plus Umgebungsvariable einigen — dann ist die
nächste Rotation ein Schritt statt zwei.

### 17. `.gitignore` aufräumen

**Aufwand:** 20 min · **Nutzen:** gering · **Prio:** P3

Auskommentierte Altblöcke und ein `*.json`-Ausschluss, der mehrere Ausnahmen
nach sich zieht.

### 18. mk-README angleichen

**Aufwand:** 1 h · **Nutzen:** gering · **Prio:** P3

Die ts-README hat seit dem 22.09. Property-Tabelle, Delta zum Vorlauf und eine
englische Grafik; die mk-README nichts davon. Damals bewusst zurückgestellt.
Das Datumsformat des Erkennungszeitraums ist mit #7 schon korrigiert.

---

## Später — wenn die übrigen Kampagnen umgestellt werden

### 2. Bildauswahl in tempo30 korrigieren

**Aufwand:** 1–2 h · **Nutzen:** hoch · **Prio:** später

`get_image_id` nimmt `images[-1]`, das letzte Element einer unsortierten Liste.
An 600 Bremer Radwegzeichen war das in 84 % nicht das neueste Bild, in 10 %
lag über ein Jahr dazwischen (Messung in `cw_campaign.newest_image_ids`).
Zusätzlich schluckt `except Exception: return None` jeden Fehler still.

- `schools_tempo30_campaign/1_merge_…` auf `cw.newest_image_ids` umstellen —
  die Challenge 52985 ist öffentlich.
- Derselbe Code steckt in access_restrictions und rad_frei. Ob sich das lohnt,
  entscheidet #6.

Am 17.10. zurückgestellt: Die übrigen Kampagnen werden später umgestellt, dann
zusammen mit #12. Die Tempo-30-Daten sind ohnehin von 08/2025 — die nächste
Runde braucht neue OSM-Daten, und mit ihr kommt dieser Fix.

### 8. tippecanoe-Funktion ins Modul

**Aufwand:** 1–2 h · **Nutzen:** mittel · **Prio:** später

`gzgjson_to_pmtiles_dual_layer` steht dreimal kopiert in den Notebooks:
in beiden `radinfra_2_pmtiles` und in access_restrictions. Die beiden
tippecanoe-Fixes (atomares Schreiben, `--no-tile-size-limit`) mussten
schon je zweimal eingebaut werden — genau das Muster, durch das am 26.08.
DE-NW verloren ging. Die Kopie in access_restrictions hat keinen der beiden
Fixes bekommen. Die zwei Kopien der Cycleway-Kampagnen sind identisch.

Am 17.10. zurückgestellt, zusammen mit #12: erst wenn die übrigen Kampagnen
umgestellt werden.

### 12. Generisches `campaign.py`

**Aufwand:** 1 Tag für den Schnitt, dann ½ Tag je Kampagne · **Nutzen:** mittel · **Prio:** später

`get_image_id`, `parallel_get_image_ids`, `mark_intersections`,
`months_between` und `to_maproulette_geojson_with_links` stehen in den
`1_merge_…`-Notebooks von fünf Kampagnen (die Kopien der Cycleway-Kampagnen
sind mit #7 weggefallen). Für alle gibt es in `cw_campaign.py` schon ein
Gegenstück: `distance_to_nearest` (gleiches CRS 25833, gleiche Treffer),
`months_seen` (dieselbe Rechnung), `newest_image_ids`, `build_maproulette_geojson`. Die Hälfte von `cw_campaign.py` ist schon generisch: Laden,
Abstand, Bilder, MapRoulette-GeoJSON. Diesen Teil als `campaign.py`
herausziehen; `cw_campaign.py` behält Zeichen, README und radinfra-Export.
Kampagnen einzeln umziehen, wenn sie ohnehin angefasst werden — nach #6.

Am 17.10. bewusst verschoben: Für die beiden Cycleway-Kampagnen drückt der
Schuh hier nicht. Der Schnitt kommt, wenn die erste weitere Kampagne umgestellt
wird.

---

## Optional

### 19. Zweiter History-Rewrite

**Aufwand:** ½ Tag · **Nutzen:** gering · **Prio:** optional

`.git` ist wieder 211 MB — gewachsen bis zum 02.09. durch
`ts_output/*.pmtiles` und die Outputs von `2_`/`2b_`. Die Ursache ist
abgestellt, es wächst nicht weiter. Ein Rewrite macht alle Clones ungültig,
und auf dem Server hat schon ein Branch-Wechsel Daten gekostet. Nur, wenn die
Größe konkret stört.

### 20. Streaming-Export

**Aufwand:** 1 Tag · **Nutzen:** gering · **Prio:** optional

`ParquetWriter` statt Sammeln und `pd.concat`. Nur nötig, wenn der Worker
trotz 8-GB-Swap wieder am Speicher stirbt.

### 21. Ende-zu-Ende-Test im Image

**Aufwand:** ½ Tag · **Nutzen:** gering · **Prio:** optional

Die Notebooks einmal per nbconvert im Worker-Image gegen einen Mini-Tile-Cache
laufen lassen. Fängt Import- und Pfadfehler, die die Unit-Tests nicht sehen.
Seit #13 betrifft das nur noch die Kampagnen-Notebooks; der Kachelabruf ist
ein Python-Aufruf mit eigenem Test.

### 22. Commit-Sperre für Tokens

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** optional

Ein Pre-Commit-Hook, der jeden Commit mit einem Mapillary-Token
(`MLY|…|<32 hex>`, roh oder URL-kodiert) ablehnt. Er hätte alle Lecks von
2025/26 aufgehalten. Seit #1 schwärzt `mapillary_tiles.py` den Token selbst,
und Notebook-Ausgaben werden nicht mehr automatisch committet — der Hook wäre
die dritte Sicherung. Wirkt nur in Klonen, in denen er eingerichtet ist
(`git config core.hooksPath .githooks`).

---

## Erledigt

### 4. Kopfzellen der `radinfra_1_export` korrigieren

**Erledigt:** 17.10.2026

Beide Notebooks sagten noch „`x_` läuft wöchentlich auf dem Server und bleibt
unverändert" und nannten sich „Schlankere Fassung von `radinfra_1_export.ipynb`".
Die Kopfzellen beschreiben jetzt, was das Notebook tut; dasselbe für beide
`maproulette_tasks`, die sich noch über `1_` erklärten.

### 7. Alte Notebooks entfernen

**Erledigt:** 17.10.2026, nach je vier grünen Cron-Läufen mit `radinfra_1_export`
(ts 23.09.–14.10., mk 24.09.–15.10., jeweils 16/16 Länder). Entfernt:

- `x_…generateOutput_2radinfra.ipynb` und `1_merge_…` in beiden
  Cycleway-Kampagnen
- `ts_output_ref/`, `mk_output_ref/` und ihre Einträge in `.gitignore`
- Abschnitt 7 „Gegenprobe" in beiden `radinfra_1_export`
- der Rückweg-Kommentar in `scripts/run_mapillary_notebooks.sh`
- in der mk-README den Zeitraum als Datum statt „2014-03-30 00:00:00" —
  der Kommentar dort sagt selbst, das lohne erst nach dem Umstieg

---

## Erledigt oder hinfällig aus den alten Dokumenten

**`docker-improvements.md`** (März 2026): alle vier TODOs erledigt —
`docker compose` statt `docker-compose`, kein `version:` mehr in den
Compose-Dateien, der Runner liest `ts`/`mk`, ein `timeout` umschließt den
ganzen Lauf.

**`plan_notebooks_zu_python.md`** (September 2026):
- Schritte 0 und 1 erledigt; 2–6 stehen hier als #14, #13, #9, #11, #10.
- B2-Upload „warnt nur" → #3.
- PMTiles und GeoJSON in git → erledigt, seit 02.09. nur noch auf B2.
- `gzgjson_to_pmtiles_dual_layer` doppelt → #8.
- `docs/` in `.gitignore` → erledigt, `docs/` wird jetzt getrackt.
- `--abort-on-container-exit` → hinfällig, seit beide Repos eigene
  Compose-Projektnamen haben.
- mk-Lauf vom 27.08. nicht rekonstruierbar → hinfällig, `RunLog` schreibt
  `logs/{ts,mk}_run_latest.log`.
- Randnotiz zum coverage-Repo (Export trotz Fehlern) → dort inzwischen
  behoben, `process_bundesland` prüft `max_fail_ratio`.
- Streaming-Umbau → #20.

**`worker_mix_fehleranalyse_und_todos.md`** (Juni 2026, nie getrackt, am 17.10.
gelöscht): Tasks 1–8 erledigt;
9 und 10 wurden damals verworfen, sind aber inzwischen umgesetzt (PMTiles und
GeoJSON liegen auf B2, nicht mehr in git); 11 im Juli erledigt (Rewrite
4,3 GB → 58 MB), zum erneuten Wachstum siehe #19; 12 → #5.
