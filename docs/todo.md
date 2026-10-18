# TODO

**Stand:** 2026-10-18

Ersetzt `plan_notebooks_zu_python.md`, `docker-improvements.md` und
`worker_mix_fehleranalyse_und_todos.md`. Was dort noch offen war, steht hier;
was erledigt oder hinfällig ist, listet der letzte Abschnitt. Die beiden
getrackten alten Dokumente liegen in der git-History (letzter Stand `9088bd5`),
`worker_mix_…` war nie getrackt und ist seit dem 17.10. gelöscht.

Am 18.10. eingearbeitet: die Durchsicht vom 17.10. aus einer Cloud-Sitzung (Bundle
`mapillary_trafficsigns_branches.bundle`, Branches `todo-durchsicht`, `src-paket`,
`mk-monatlich`) — #24–#28 und Ergänzungen in #8, #14, #15, #17. Gemergt ist keiner der
Branches: sie setzen auf dem Stand vor dem Modulschnitt (#12) auf.

**Aufwand** ist grobe Arbeitszeit. **Nutzen:** hoch / mittel / gering.
**Prio:** P1 = bald · P2 = als Nächstes · P3 = bei Gelegenheit · optional = nur bei Bedarf ·
später = bewusst zurückgestellt, bis die übrigen Kampagnen umgestellt werden (Entscheidung 17.10.).

## Übersicht

| # | Aufgabe | Aufwand | Nutzen | Prio |
|--:|:--------|:--------|:-------|:-----|
| 1 | Mapillary-Token rotieren, `config.py` löschen | 5 min Rest | hoch | P1, fast ✅ |
| 2 | Bildauswahl in tempo30 korrigieren | 1–2 h | hoch | ✅ 18.10. |
| 3 | Fehlschläge melden | 1 h | hoch | ✅ 17.10. |
| 4 | Kopfzellen der `radinfra_1_export` korrigieren | 15 min | mittel | ✅ 17.10. |
| 5 | Deploy-Weg festlegen | 30 min | mittel | ✅ 17.10. |
| 6 | Kampagnen-Inventur | 30 min | mittel | ✅ 18.10., Entscheidungen offen |
| 7 | Alte Notebooks entfernen (ab 08.10.) | 1 h | mittel | ✅ 17.10. |
| 8 | tippecanoe-Funktion ins Modul | 1–2 h | mittel | P3 |
| 9 | Eine Python-Umgebung (uv) | ½ Tag | mittel | ✅ 17.10. |
| 10 | CI | 1 h | hoch | ✅ 17.10. |
| 11 | Notebook-Outputs aus git | 30 min | mittel | ✅ 17.10. |
| 12 | Generisches `campaign.py` | ½ Tag je weitere Kampagne | mittel | ✅ 18.10. |
| 13 | CLI statt Root-Notebooks | ½ Tag Rest | gering | P3, Kern ✅ 17.10. |
| 14 | `src/`-Paketstruktur | ½ Tag | gering | P3 |
| 15 | `docs/betrieb.md` | 1 h | mittel | P3 |
| 16 | Token-Quellen vereinheitlichen | 30 min | gering | P3 |
| 17 | `.gitignore` und veraltete Kommentare aufräumen | 30 min | gering | P3 |
| 18 | mk-README angleichen | 1 h | gering | ✅ 17.10. |
| 19 | Zweiter History-Rewrite | ½ Tag | gering | ✅ 17.10. |
| 20 | Streaming-Export | 1 Tag | gering | optional |
| 21 | Ende-zu-Ende-Test im Image | ½ Tag | gering | optional |
| 22 | Commit-Sperre für Tokens | 30 min | mittel | optional |
| 23 | Kampagnen-Erstellung auf dem Server testen | ½ Tag | mittel | P2 |
| 24 | B2: alte Versionen nach 90 Tagen löschen | 15 min | gering | P3 |
| 25 | Feature-ID-Regel richtigstellen | 30 min | mittel | P2 |
| 26 | Parquet und Metadaten atomar schreiben | 30 min | mittel | P2 |
| 27 | CI baut das Worker-Image | 1 h | hoch | P1, vor dem Merge von #9-Branch |
| 28 | mk nur noch monatlich | 30 min | gering | optional, Entscheidung offen |

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

### 27. CI baut das Worker-Image

**Aufwand:** 1 h · **Nutzen:** hoch · **Prio:** P1 — vor dem Merge von `chore/remove-unused-deps`

Der Auto-Deploy (#5) rollt einen Commit aus, sobald die Tests grün sind. Das
Worker-Image baut aber erst der Server, beim nächsten Lauf: Ein Fehler im
Dockerfile oder in `uv.lock` fällt erst als gescheiterter Wochenlauf auf. Ein
zweiter CI-Job baut `docker/Dockerfile.worker` und ruft darin tippecanoe,
`python3 -m mapillary_pipeline --help`, den Import der Kampagnen-Module und
`jupyter nbconvert --version` auf, mit dem Repo per Bind-Mount unter `/app` wie auf
dem Server. Der Deploy wartet automatisch auch auf diesen Job, weil er alle
Check-Runs des Commits prüft.

Dringend macht das der Branch `chore/remove-unused-deps` (#9, 18.10.): Er ändert
`uv.lock` und damit das Image. Reihenfolge: erst dieser Job, dann der Merge — nach
den Läufen am 21./22.10.

Vorlage: Der Branch `src-paket` der Durchsicht hat den Job schon, setzt aber das
Paket aus #14 voraus; die Smoke-Tests sind an den heutigen Aufbau anzupassen.
Ausbaustufe: #21.

---

## P2 — als Nächstes

### 6. Kampagnen-Inventur

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** P2 — Inventur ✅ 18.10., drei Entscheidungen offen

Stand am 18.10.2026, laut MapRoulette (Projekte 60811 und 61738, beide vizsim/bicyclett):

| Ordner | Challenge | Status | offen | Daten | Code |
| --- | --- | --- | --: | --- | --- |
| `cycleway_complete_campaign` | 52916 | aktiv | 242 | Mapillary 14.10., OSM 17.10.2026 | umgestellt; dazu wöchentlicher radinfra-Export |
| `cycleway_complete_marking_campaign` | 53882 | aktiv | 617 | Mapillary 15.10., OSM 17.10.2026 | umgestellt; dazu Export |
| `pedestrian_crossing_campaign` | 53589 | aktiv | 183 | 14.10. / 17.10.2026 | umgestellt |
| `access_restrictions_campaign` | 54768 | aktiv | 2.044 + 1.157 Skipped | 14.10. / 17.10.2026 | umgestellt |
| `schools_tempo30_campaign` | 52985 | **archiviert** | 982 | 14.10. / 17.10.2026 | umgestellt |
| `maxspeed_accidents_campaign` | noch keine | — | 390 in der Datei | 14.10. / 17.10.2026, Unfälle 03.10.2026 | neu 18.10. |
| `pedestrian_crossing_marking_campaign` | 53697 | archiviert, deaktiviert — bleibt so | 61 | 11/2025; Datei mit 465 (15.10. / 17.10.2026) | umgestellt 18.10. |
| `rad_frei_campaign` | keine (53361, im Code verlinkt, ist gelöscht) | — | — | 10/2025 | gelöscht 18.10., Tag `archive/rad_frei` |
| `analysis/analize_osm_ts.ipynb` | — | — | — | 12/2025 | Einzelstück |

Was die drei alten sind:

- **pedestrian_crossing_marking** — Zebrastreifen-Markierungen ohne `highway=crossing` in
  50 m. Fachlich die Zwillingskampagne von pedestrian_crossing: gleicher Abgleich, gleiches
  Zusammenfassen, nur Map-Feature-Punkte statt Verkehrszeichen. Hat noch die Bildsuche über
  Blickwinkel, eine eigene Kopie des Überweg-Auszugs von 11/2025 und `.explore()` (folium).
  Umstellen wäre wenig Arbeit: `pc_campaign.py` und der Überweg-Auszug passen schon.
- **rad_frei** — Zusatzzeichen DE:1022-10 (Radfahrer frei) und 1000-33 ohne freigegebenen
  Radverkehr (`bicycle=yes|designated`, `oneway:bicycle=no`, `share_busway`, …) in 30 m. Keine
  Challenge mehr; Code mit `images[-1]`, `../../config.json` und dem Glob über alle Parquets.
  Die Zeichen exportiert der wöchentliche radinfra-Lauf schon.
- **analysis/analize_osm_ts.ipynb** — Overpass-Abfrage: OSM-Knoten mit `traffic_sign~DE:240`
  und `mapillary=*` in Brandenburg, dazu das Aufnahmedatum des verlinkten Bilds. Einmalige
  Auswertung, liest `../config.json` und als einziges `osm2geojson`.

Offen:

- **Challenge für maxspeed_accidents anlegen** (neu 18.10.); die Schritte stehen in deren README.
- **52985 entarchivieren.** Die 982 Aufgaben der neuen Runde stehen in einer archivierten
  Challenge — für Mapper unsichtbar.
- pedestrian_crossing_marking ist am 18.10. umgestellt. 53697 bleibt aber archiviert: die
  Zebrastreifen-Erkennungen liefern zu viele Falsch-Positive (Entscheidung 18.10.).
- rad_frei ist am 18.10. gelöscht. Der Tag `archive/rad_frei` zeigt auf den letzten Stand;
  zurückholen mit `git checkout archive/rad_frei -- use_cases/rad_frei_campaign`.
- Offen: das Analyse-Notebook.
- Danach räumt #9 `pyproject.toml` auf: `fiona`, `folium` und `mapillary` (das alte SDK,
  bringt scipy und turfpy mit) nutzt seit 18.10. niemand mehr, `osm2geojson` nur noch das
  Analyse-Notebook. Das ändert das Worker-Image — also nicht direkt vor einem Cron-Lauf.

### 23. Kampagnen-Erstellung auf dem Server testen

**Aufwand:** ½ Tag · **Nutzen:** mittel · **Prio:** P2

Ziel: die `maproulette_tasks`-Notebooks nicht nur lokal, sondern auf dem Server
laufen lassen. pedestrian_crossing ist der Testfall — seine Challenge ist
abgeschlossen, ein Fehlschlag trifft niemanden. Beide Notebooks laufen unverändert
per nbconvert; was ein Serverlauf setzen muss (`OSM_EXTRACTS`, `CAMPAIGN_SYNC=0`,
`CAMPAIGN_OUTPUT_DIR`), steht in `use_cases/pedestrian_crossing_campaign/README.md`.

Offen:

- `osmium` fehlt im Worker-Image. Als eigene `RUN`-Schicht hinter tippecanoe
  ergänzen und das Image einmal von Hand bauen, bevor der nächste Cron-Lauf es tut —
  sonst hängt dessen `--build` an apt.
- Wo und wie: `docker compose run` ohne VPN-Overlay, außerhalb der Cron-Fenster,
  und denselben Lock nehmen wie die Worker (`/tmp/mapillary_worker.lock`).
- Platz für den Geofabrik-Auszug (4,8 GB) auf dem Server prüfen.
- Zugangsdaten: Steht `API_KEY_MAPROULETTE` in der `config_mapillary_privat.json`
  auf dem Server?
- Wohin mit dem Ergebnis: Upload per MapRoulette-API ist gebaut
  (`campaign.upload_tasks`, im Notebook nur mit `CAMPAIGN_UPLOAD=1`), läuft
  aber noch nicht: Seit maproulette-backend v4.11.0 (Sicherheitsvorfall Oktober
  2026) sind API-Keys abgeschaltet, jedes Skript bekommt 401. Ersatz sind
  Personal Access Tokens (`Authorization: Bearer mrt_…`), am 18.10. nur ein
  Vorschlag ohne Zeitplan (maproulette-backend#1288). Bis dahin holt MapRoulette
  die Aufgaben weiter über `remoteGeoJson`, und „Rebuild tasks“ bleibt ein Klick.
  Die Datei woandershin legen (data.vizsim.de) hilft nicht: Hat eine Challenge
  Aufgaben, sperrt die Oberfläche ihre Quell-URL (maproulette3,
  `isSourceReadOnly`). Der Serverbetrieb lohnt sich deshalb erst, wenn der
  Upload geht — bis dahin muss das Ergebnis über einen Push nach GitHub.

### 25. Feature-ID-Regel richtigstellen

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** P2

Die README der Verkehrszeichen-Kampagne sagt: „Never renumber the row index. It
becomes the `id` of each feature in the GeoJSON and the vector tiles, and
radinfra.de depends on it." Docstrings, Tests und Notebook-Zellen wiederholen das.
Für die Vector Tiles stimmt es nicht: `GeoDataFrame.to_json()` schreibt die id als
String (`"id": "45"`), tippecanoe verwirft sie mit „Can't represent non-numeric
feature ID". Die PMTiles tragen keine Feature-ids, nur die Mapillary-`id` als
Property — am 18.10. mit tippecanoe 2.78.0 nachgeprüft. Dazu kommt: `load_features`
nummeriert per `ignore_index=True` neu, die id ist also nur innerhalb eines Laufs
eindeutig.

- Klären, was radinfra.de tatsächlich nutzt: die Top-Level-id der GeoJSON, die
  Mapillary-`id` als Property oder keins von beiden.
- Danach angleichen: `cycleway_complete_campaign/README.md` („Before changing the
  code"), die Docstrings von `load_features`, `clip_to_boundary` und
  `filter_stable_signs` in `campaign.py`, die Testbeschreibungen in
  `test_campaign.py` und die Zellen in beiden `radinfra_1_export`.
- Sollen die Tiles ids tragen: tippecanoe mit `--convert-stringified-ids-to-numbers`
  (laut Durchsicht: schreibt den Index als MVT-id, die PMTiles werden gut 10 %
  größer).

### 26. Parquet und Metadaten atomar schreiben

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** P2

`export_geodata` in `mapillary_pipeline.py` schreibt das Parquet direkt unter dem
endgültigen Namen, `_write_metadata` die JSON per `open(path, "w")` — am 18.10.
nachgesehen. Stirbt der Prozess genau dabei — mk-Läufe sind schon an der
Speichergrenze gestorben —, bleibt eine halbe Datei liegen. An einer kaputten
Metadatei scheitert jeder Folgelauf schon beim Lesen, ein halbes Parquet bricht
`radinfra_1_export` ab, Lauf für Lauf, bis jemand aufräumt. Wie an den übrigen
Stellen im Repo: nach `*.tmp` schreiben, dann `os.replace`. Die Endung muss `.tmp`
sein, nicht `.tmp.parquet`: dann trifft weder der Upload-Include noch das Glob in
`load_features` eine liegengebliebene Datei.

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
`src/mapillary_trafficsigns/` macht die Pfad-Tricks überflüssig — die eine
Umgebung aus #9 allein tut das nicht.

Zielbild, nach dem Schnitt aus #12:

```text
src/mapillary_trafficsigns/
    tiles.py              ← mapillary_tiles.py
    pipeline.py           ← mapillary_pipeline.py, dazu die CLI mapillary-pipeline
    campaigns/
        common.py         ← use_cases/campaign.py
        cycleway.py       ← use_cases/cw_campaign.py
        crossings.py      ← use_cases/pc_campaign.py
        access.py         ← use_cases/ar_campaign.py
        tempo30.py        ← use_cases/t30_campaign.py
    (vectortiles.py)      ← später die tippecanoe-Funktion, #8
tests/                    alle Tests, auch die der Kampagnen
use_cases/                nur noch Notebooks und Daten
```

- `pyproject.toml`: `uv_build` als Build-Backend, `package = true`. `uv sync`
  installiert das Paket editierbar; die Notebooks importieren
  `from mapillary_trafficsigns.campaigns import common as campaign`, ohne `sys.path`.
- Dockerfile: erst nur die Abhängigkeiten (`--no-install-project`), nach `COPY . .`
  das Paket selbst. Dessen `.pth` zeigt auf `/app/src`, also auf den Code im
  Bind-Mount, den der Auto-Deploy aktuell hält.
- Runner: `python3 -m mapillary_trafficsigns.pipeline ts|mk`.
- Pfade bleiben relativ zum Arbeitsverzeichnis; nichts im Code hängt an `__file__`.
- Erst verschieben, dann ändern — sonst zeigt der Diff nicht, was sich inhaltlich
  geändert hat. #8 deshalb nicht im selben Schritt.

Der Branch `src-paket` der Durchsicht setzt das um, aber auf dem Stand vor dem
Schnitt aus #12 (nur `cw_campaign.py`). Nicht mergen, neu aufsetzen.

### 15. `docs/betrieb.md`

**Aufwand:** 1 h · **Nutzen:** mittel · **Prio:** P3

Das Betriebswissen steht verstreut in Commit-Messages: Cron-Zeiten (ts Mi
15:00 UTC, mk Do 01:00 UTC), der automatische Deploy (#5) und healthchecks.io
(#3), Wiederherstellen aus B2 (frühere Versionen 90 Tage lang, sobald #24
eingerichtet ist), auf dem
Server `checkout -B main origin/main` statt Branch-Wechsel (ein Wechsel hat
am 16.09. die ignorierten Lauf-Outputs gelöscht), Aussetzen und
Wiederherstellen des Crontabs, `max_file_age_days` und manuelle Läufe. Dazu,
wer die veröffentlichten Dateien liest: radinfra.de, und unfallkarte bindet die
PMTiles als „external"-Layer über ihre feste URL auf data.vizsim.de ein —
Dateinamen und Pfade dort dürfen sich nicht beiläufig ändern. Eine Seite dafür.

### 16. Token-Quellen vereinheitlichen

**Aufwand:** 30 min · **Nutzen:** gering · **Prio:** P3

Es bleiben zwei Dateien: `config.json` (Pipeline, analysis) und
`use_cases/utils/config_mapillary_privat.json` (Kampagnen, dazu der
MapRoulette-Key). Die alten Kampagnen-Notebooks lesen die zweite direkt ein,
deshalb passt das zu #12. Beide Loader lesen `MAPILLARY_ACCESS_TOKEN` schon aus der
Umgebung. Auf eine Datei plus Umgebungsvariable einigen — dann ist die
nächste Rotation ein Schritt statt zwei.

### 17. `.gitignore` und veraltete Kommentare aufräumen

**Aufwand:** 30 min · **Nutzen:** gering · **Prio:** P3

Auskommentierte Altblöcke und ein `*.json`-Ausschluss, der mehrere Ausnahmen
nach sich zieht. Dazu Kommentare, die einen alten Stand beschreiben (Durchsicht):
`.gitignore` verweist auf „Task 1" und „Task 3" eines gelöschten Plans,
`docker/.env.example` nennt den B2-Key nur für die ts-Parquets.

- ✅ 18.10.: `upload_outputs_to_b2.sh` sagte noch, die Kampagnen-Outputs stünden
  „aktuell ZUSÄTZLICH noch in git" (seit 02.09. nicht mehr, `COMMIT_PATHS` gibt es
  nicht mehr), und erklärt jetzt, warum Aufräumen in B2 keine Sache von
  `b2 sync --keep-days` ist (#24).

### 24. B2: alte Versionen nach 90 Tagen löschen

**Aufwand:** 15 min · **Nutzen:** gering · **Prio:** P3

Der Bucket `vizsim-public-archive` behält jede frühere Fassung: Jeder Lauf lädt die
`*_latest`-Dateien unter demselben Namen hoch — rund 160 MB ts-Parquets und knapp
1 GB mk-Parquets pro Lauf, dazu die Kampagnen-Dateien. Die Kosten liegen im
Cent-Bereich, aber es wächst ohne Ende. Ziel: frühere Versionen 90 Tage behalten,
dann löschen; die aktuelle Version bleibt immer stehen.

Das gehört in eine Lifecycle-Regel des Buckets, nicht ins Upload-Skript.
`b2 sync --keep-days` räumte alte Versionen zwar auch ab, versteckt aber jede
Datei im Ziel, die lokal fehlt: ein Land, dessen Parquet einmal nicht exportiert
wurde, verschwände von data.vizsim.de.

Einmalig einrichten, mit einem Key, der Bucket-Einstellungen ändern darf (der
Upload-Key `B2_ARCHIVE_KEY` darf das in der Regel nicht):

- **Web-UI:** Buckets → `vizsim-public-archive` → Lifecycle Settings → „Use custom
  lifecycle rules", zwei Regeln mit leerem „Days till hide" und 90 bei „Days till
  delete": `mapillary_trafficsigns/` und `mapillary_map-feature-points/`. Nur diese
  Präfixe, weil im Bucket auch andere Projekte liegen.
- **CLI (b2 ≥ 4):** vorher `b2 bucket get vizsim-public-archive` ansehen —
  `bucket update` setzt alle Regeln auf einmal, vorhandene müssen mit in den Aufruf:

  ```bash
  b2 bucket update \
    --lifecycle-rule '{"fileNamePrefix": "mapillary_trafficsigns/", "daysFromHidingToDeleting": 90, "daysFromUploadingToHiding": null}' \
    --lifecycle-rule '{"fileNamePrefix": "mapillary_map-feature-points/", "daysFromHidingToDeleting": 90, "daysFromUploadingToHiding": null}' \
    vizsim-public-archive
  ```

Prüfen: `b2 bucket get --show-size vizsim-public-archive` zählt alle Versionen mit.
B2 wendet die Regeln einmal täglich an; nach zwei Tagen sollte die Größe deutlich
gefallen sein. Wiederherstellen geht weiter, solange eine Version jünger als 90
Tage ist — rund 13 Wochenstände. Das gehört dann mit nach `docs/betrieb.md` (#15).

---

## Später — wenn die übrigen Kampagnen umgestellt werden

### 2. Bildauswahl in tempo30 korrigieren

**Aufwand:** 1–2 h · **Nutzen:** hoch · **Prio:** später

`get_image_id` nimmt `images[-1]`, das letzte Element einer unsortierten Liste.
An 600 Bremer Radwegzeichen war das in 84 % nicht das neueste Bild, in 10 %
lag über ein Jahr dazwischen (Messung in `cw_campaign.newest_image_ids`).
Zusätzlich schluckt `except Exception: return None` jeden Fehler still.

- ✅ 18.10.: schools_tempo30 nutzt `campaign.newest_image_ids` (#12). Dabei fiel
  auf, dass die Runde 2025 Bild- und Erkennungs-ID vertauscht hatte: die
  Aufgaben in 52985 hießen nach dem Bild. Die neue Runde ersetzt sie.
- Derselbe Code steckte in access_restrictions und rad_frei: die erste ist seit
  18.10. umgestellt, die zweite gelöscht (#6).

Am 17.10. zurückgestellt: Die übrigen Kampagnen werden später umgestellt, dann
zusammen mit #12. Die Tempo-30-Daten sind ohnehin von 08/2025 — die nächste
Runde braucht neue OSM-Daten, und mit ihr kommt dieser Fix.

### 8. tippecanoe-Funktion ins Modul

**Aufwand:** 1–2 h · **Nutzen:** mittel · **Prio:** später

`gzgjson_to_pmtiles_dual_layer` steht zweimal kopiert in den Notebooks, in
beiden `radinfra_2_pmtiles`; die Kopien sind identisch. Die beiden
tippecanoe-Fixes (atomares Schreiben, `--no-tile-size-limit`) mussten
schon je zweimal eingebaut werden — genau das Muster, durch das am 26.08.
DE-NW verloren ging. Eine dritte Kopie in access_restrictions, ohne beide
Fixes und ohne Eingabe, ist am 18.10. gelöscht.

Am 17.10. zurückgestellt, zusammen mit #12: erst wenn die übrigen Kampagnen
umgestellt werden. Seit 18.10. ist das erfüllt — jetzt P3.

Beim Umzug gleich `--no-feature-limit` dazunehmen (Durchsicht, nachgestellt am
17.10. mit 230.000 Punkten in einer z7-Kachel): Neben der 500-KB-Grenze kennt
tippecanoe eine zweite, 200.000 Features je Kachel. Mit `--drop-rate=0` hat es
auch dort kein Ventil und bricht mit Exit 110 ab, wie am 16.06. Die dichteste
z7-Kachel der ts-Daten hatte im April knapp 30.000 Features — weit weg, aber
dieselbe Falle.

Ebenfalls am 17.10. geprüft: tylertoo (GeoParquet → PMTiles, Rust) als Ersatz für
tippecanoe. Gleicher Inhalt, aber kaum schneller (ts: 7 s statt 10 s auf 2 Kernen),
drei- bis vierfacher RAM-Bedarf und mit v0.8 noch Breaking Changes. Bleibt bei
tippecanoe, bis das Kacheln Minuten statt Sekunden dauert.

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

- ✅ 18.10.: Schnitt gemacht, mit pedestrian_crossing als erster weiterer
  Kampagne. `campaign.py` hat die generischen Schritte, unverändert verschoben;
  `cw_campaign.py` exportiert sie weiter, die Cycleway-Notebooks blieben
  unberührt. Beide `radinfra_1_export` liefern danach denselben Inhalt wie vorher
  (GeoJSON, README und Historie gleich, SVG bis auf Datum und Clip-IDs). Neu in
  `campaign.py`: `dedupe_nearby` (Zeichen derselben Stelle zusammenfassen) und
  eine feste Wahl zwischen gleich alten Bildern in `newest_image_ids` — vorher
  schwankte sie mit der Reihenfolge der API.
- ✅ 18.10.: access_restrictions umgestellt (`ar_campaign.py`); die
  cosmo-Variante ist weg, der Auszug kommt aus `0_prepare_osm_network`.
- ✅ 18.10.: schools_tempo30 umgestellt (`t30_campaign.py`), damit auch #2.
- ✅ 18.10.: pedestrian_crossing_marking umgestellt, teilt `pc_campaign.py` mit
  pedestrian_crossing.
- ✅ 18.10.: rad_frei gelöscht (Tag `archive/rad_frei`, #6). Damit läuft jede
  Kampagne auf `campaign.py`; SDK, fiona und folium können aus `pyproject.toml`
  (#9), osm2geojson erst mit dem Analyse-Notebook.

---

## Optional

### 20. Streaming-Export

**Aufwand:** 1 Tag · **Nutzen:** gering · **Prio:** optional

`ParquetWriter` statt Sammeln und `pd.concat`. Nur nötig, wenn der Worker
trotz 8-GB-Swap wieder am Speicher stirbt.

### 21. Ende-zu-Ende-Test im Image

**Aufwand:** ½ Tag · **Nutzen:** gering · **Prio:** optional

Die Notebooks einmal per nbconvert im Worker-Image gegen einen Mini-Tile-Cache
laufen lassen. Fängt Import- und Pfadfehler, die die Unit-Tests nicht sehen.
Seit #13 betrifft das nur noch die Kampagnen-Notebooks; der Kachelabruf ist
ein Python-Aufruf mit eigenem Test. Ausbaustufe von #27, das nur prüft, ob im
Image alles startet.

### 28. mk nur noch monatlich

**Aufwand:** 30 min · **Nutzen:** gering · **Prio:** optional — Entscheidung offen

Vorschlag der Durchsicht: Fahrbahnmarkierungen ändern sich langsam, der Wochenlauf
bringt wenig Neues, belegt aber Server, VPN und B2. Dagegen spricht: radinfra.de
bekäme die Markierungen nur noch monatlich, und ein übersprungener Lauf (Lock von
ts belegt, Land an der Reißleine) kostet einen Monat statt einer Woche. Das
Speicherargument erledigt #24.

Falls doch, am ersten Donnerstag im Monat, 01:00 UTC:

- **Crontab:** cron verknüpft Tag im Monat und Wochentag mit ODER — `0 1 1-7 * 4`
  liefe an jedem Donnerstag *und* an jedem der ersten sieben Tage. Deshalb den
  Wochentag im Befehl prüfen (`%` muss in der Crontab maskiert werden):
  `0 1 1-7 * * [ "$(date -u +\%u)" = 4 ] && <bisheriger mk-Befehl>`
- **healthchecks.io:** mk-Check auf den Cron-Ausdruck `0 1 * * 4#1` (UTC) umstellen,
  Grace Time bleibt 10 h — sonst meldet er jeden Donnerstag einen fehlenden Lauf.
- **Texte** (Notebook-Kopf, READMEs, veröffentlichte README „weekly … every
  Thursday"): Der Branch `mk-monatlich` der Durchsicht hat sie, auf dem Stand vom
  17.10. — neu aufsetzen, am selben Tag wie die Crontab mergen.

### 22. Commit-Sperre für Tokens

**Aufwand:** 30 min · **Nutzen:** mittel · **Prio:** optional

Ein Pre-Commit-Hook, der jeden Commit mit einem Mapillary-Token
(`MLY|…|<32 hex>`, roh oder URL-kodiert) ablehnt. Er hätte alle Lecks von
2025/26 aufgehalten. Seit #1 schwärzt `mapillary_tiles.py` den Token selbst,
und seit #11 kommen Notebook-Ausgaben gar nicht mehr in einen Commit — der
Hook wäre die dritte Sicherung. Wirkt nur in Klonen, in denen er eingerichtet ist
(`git config core.hooksPath .githooks`).

---

## Erledigt

### 19. Zweiter History-Rewrite

**Erledigt:** 17.10.2026 — `.git` 206 MB → 29 MB.

86 % der History waren 24 Dateien: je sechs Wochenstände (22.07.–02.09.) von
`*_latest.pmtiles` und `*_latest.geojson.gz` aus `ts_output/` und
`mk_output/`, die seitdem nur noch auf B2 liegen. Nur diese vier Pfade sind
entfernt (`git filter-repo --invert-paths --prune-empty never`). Dadurch haben
nur die 65 Commits ab dem 22.07.2026 neue SHAs, die 185 davor sind
unverändert; der Stand von `main` ist bitgleich.

Bewusst geblieben: Code und Doku, die Quelltexte der gelöschten Notebooks,
die Eingabedateien, die MapRoulette-GeoJSONs und die Notebook-Outputs bis
zum 17.10. Diese Outputs zu entfernen hätte fast alle SHAs geändert, für
etwa 15 MB.

Backup des vorherigen Stands: `~/mapillary_trafficsigns_backup_2026-10-17.git`.
Der Server wurde per `reset --soft` auf denselben Code-Stand in der neuen
History gesetzt, Daten blieben unberührt. Auf GitHub halten der Fork von
tordans und PR #2 die alten Commits weiter erreichbar.

### 18. mk-README angleichen

**Erledigt:** 17.10.2026, sichtbar ab dem mk-Lauf am 22.10.

Die mk-README auf data.vizsim.de ist aufgebaut wie die ts-README:
Property-Tabelle, `## Files` mit relativen Links, englische Grafik. Dazu eine
Δ-Zeile zum Vorlauf aus `markings_history.json`, die wie `signs_history.json`
neben den Outputs liegt und mit nach B2 geht. Die Historie-Funktionen in
`cw_campaign.py` nehmen dafür einen Dateinamen.

### 11. Notebook-Outputs aus git

**Erledigt:** 17.10.2026

Notebooks werden ohne Outputs committet, die Arbeitskopie behält sie:
`.gitattributes` schickt jedes `*.ipynb` durch `nbstripout --keep-id`
(Dev-Abhängigkeit in `pyproject.toml`). Der Filter selbst steht in
`.git/config` und muss je Klon einmal eingerichtet werden; die Befehle stehen
in `.gitattributes`. Ein Klon ohne Filter fällt in der CI auf: der Schritt
„Notebooks carry no outputs" schlägt fehl, und damit wartet auch der
Auto-Deploy (#5). Der Server braucht den Filter nicht, er committet seit dem
02.09. nichts mehr.

Beim Einrichten einmal alle 20 Notebooks bereinigt: 5,3 MB → 350 KB.
Zellinhalte unverändert, nur die Schlüssel stehen jetzt in der Reihenfolge
von nbformat. Die History behält die alten Outputs (#19).

### 9. Eine Python-Umgebung (uv)

**Erledigt:** 17.10.2026

Eine Umgebung für alles: `pyproject.toml` + `uv.lock` im Repo-Root. Lokal per
`uv sync`, im Worker-Image per `uv sync --frozen` nach `/opt/venv` — nicht nach
`/app/.venv`, denn der Bind-Mount des Repos würde sie dort verdecken.
`requirements*.txt`, `use_cases/pyproject.toml`, `pytest.ini` und der Test, der
die beiden alten Listen synchron hielt, sind weg; `uv run pytest` startet alle
114 Tests.

Maßstab war das Produktions-Image vom 15.10., nicht `requirements.txt`: die Datei
pinnte nbconvert, aber nicht dessen 17 Abhängigkeiten, die pip beim Bau selbst
auflöste. Das neue Image hat dieselben Versionen wie das alte, und beide
Pipelines liefern darin dasselbe Ergebnis. Dabei entfernt, weil von nichts
benutzt: fastparquet, mapclassify, networkx, scikit-learn samt Abhängigkeiten
(8 Pakete). scipy und turfpy bleiben vorerst, weil das alte `mapillary`-SDK sie
mitbringt; mit #12 fallen SDK, fiona, folium und osm2geojson weg.

### 5. Deploy-Weg festlegen

**Erledigt:** 17.10.2026 — Auto-Pull, abgesichert über die CI (#10).

Bis dahin erreichte ein Push nach `main` den Server erst mit einem manuellen
`git pull`. Jetzt spult `run_worker_with_vpn.sh` zu Beginn jedes Laufs selbst
auf `origin/main` vor — aber nur, wenn die GitHub-Checks genau dieses Commits
grün sind. Danach startet das Skript sich neu, damit auch seine eigene neue
Fassung läuft. Bei laufenden oder roten Tests, lokalen Änderungen, abweichender
History oder nicht erreichbarem GitHub bleibt der bisherige Stand, und die
Meldung an healthchecks.io sagt, warum. Abschalten für einen Lauf:
`MAPILLARY_AUTO_DEPLOY=0`.

### 10. CI

**Erledigt:** 17.10.2026

`.github/workflows/tests.yml` führt bei jedem Push nach `main` und bei Pull
Requests beide Testordner aus, je Umgebung ein Job: `tests/` mit
`requirements-dev.txt` (wie im Worker-Image), `use_cases/` mit `uv.lock`.
Vorher lokal in einem frischen Klon nachgestellt — kein Test braucht Netz,
Zugangsdaten oder die ignorierten Daten in `output/`. Seit #9 ist es ein
einziger Job.

### 3. Fehlschläge melden

**Erledigt:** 17.10.2026

Bis dahin stand ein gescheiterter Lauf nur in `logs/cron-*.log`, und ein
übersprungener B2-Upload endete mit Exit 0 — nichts publiziert, niemand merkte es.

Jetzt meldet `run_worker_with_vpn.sh` jeden Lauf an healthchecks.io (je ein
Check für ts und mk, Ping-URLs in `docker/.env` auf dem Server): Start, dann
Erfolg oder Fehler, mit den letzten Zeilen der Lauf-Mitschrift. Als Fehler
gilt auch ein gescheiterter oder übersprungener Upload (Exit 3), ein wegen
Lock ausgefallener Lauf und ein Land, das an der Reißleine hängen blieb.
healthchecks.io alarmiert zusätzlich, wenn gar kein Lauf kommt
(Grace Time: ts 8 h, mk 10 h).

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
