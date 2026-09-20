# Kampagne „fehlende Radwege" — was hier läuft

**Stand:** 2026-09-20

In diesem Ordner laufen **zwei voneinander unabhängige Verarbeitungen**. Sie teilen sich
Eingabedaten und seit dem 20.09.2026 auch Code, werden aber von verschiedenen Leuten zu
verschiedenen Zeiten in verschiedenen Umgebungen gestartet. Diese Datei hält fest, was
wozu gehört — die Dateinamen verraten es nicht.

---

## Strang A · MapRoulette-Aufgaben

Sucht Verkehrszeichen, an denen in OSM keine Radinfrastruktur gemappt ist, und baut
daraus Aufgaben für die MapRoulette-Challenge 52916.

| | |
| --- | --- |
| **Auslöser** | von Hand, wenn eine neue Challenge-Runde ansteht |
| **Umgebung** | uv-Env aus [`use_cases/pyproject.toml`](../pyproject.toml) — `uv sync` in `use_cases/` |
| **Zusätzlich nötig** | `osmium` als CLI, MapRoulette-API-Key, Mapillary-Token |

```
../0_prepare_osm_network.ipynb                             ← gemeinsam mit der Marking-Kampagne
    Geofabrik-PBF laden → osmium tags-filter → GeoParquet
    →  ../utils/processed_osm_files/processed_cycleways_germany_<datum>.parquet   (~600 MB)

1b_merge_mapillary-trafficsigns_osm-cycleways.ipynb        ← aktuell
    Zeichen + OSM-Radinfra verschneiden, neuestes Mapillary-Bild holen
    →  maproulette_tasks_missing-cw_instruction_vz_name_new.geojson
```

`1_merge_…ipynb` ist die Vorgängerfassung. Sie bleibt liegen, solange `1b_` neu ist —
die Vergleichszelle in `1b_` misst sich daran. Unterschiede und Messwerte:
[`1b_unterschiede.md`](1b_unterschiede.md).

> **Achtung, `set_date`:** Das Datum steht in [`../0_prepare_osm_network.ipynb`](../0_prepare_osm_network.ipynb)
> **und** in `1b_` und muss übereinstimmen — seit dem 20.09.2026 zusätzlich im
> `1_merge` der Marking-Kampagne, die dieselbe Datei liest. Geofabrik hält Tagesstände
> nur rund 90 Tage vor: ist ein PBF weder lokal noch dort, lässt sich der Stand nicht
> mehr neu ableiten.

---

## Strang B · Export für radinfra.de

Veröffentlicht alle radverkehrsbezogenen Zeichen als GeoJSON und Vector Tiles.
**Das hier läuft unbeaufsichtigt in Produktion.**

| | |
| --- | --- |
| **Auslöser** | cron auf dem Server, **mittwochs 15:00 UTC** |
| **Umgebung** | pip-Env im Worker-Image aus [`requirements.txt`](../../requirements.txt), Python 3.12 |
| **Eingabe** | nur `output/*.parquet` und die statische Autobahn-Datei — kein PBF, kein osmium |

```
scripts/run_worker_with_vpn_ts.sh
  └─ scripts/run_mapillary_notebooks.sh ts
       1. 2_get_mapillary_traffic_signs.ipynb          (Repo-Wurzel, holt die Tiles)
       2. xb_mapillary-trafficsigns_generateOutput_2radinfra.ipynb   ← aktuell
             →  ts_output/mapillary_trafficsigns_bicycle_latest.geojson.gz
             →  ts_output/README.md, ts_output/signs_by_month.svg
       3. 2_create_pmtiles_from_geojson_trafficsigns.ipynb
             →  .pmtiles
  └─ scripts/upload_outputs_to_b2.sh   →  data.vizsim.de
```

`x_…ipynb` ist die Vorgängerfassung und bleibt liegen, bis `xb_` ein paar Wochen sauber
gelaufen ist. Zurückschalten heißt: in `run_mapillary_notebooks.sh` wieder `x_` eintragen.
Nachweis, dass beide dasselbe erzeugen: [`xb_unterschiede.md`](xb_unterschiede.md).

**Wenn ein Notebook scheitert**, bricht `run_worker_with_vpn.sh` mit `exit 1` ab —
**vor** dem B2-Upload. Es wird also nichts Halbes publiziert; der bisherige Stand auf
data.vizsim.de bleibt. Der Schaden eines Fehlschlags ist eine ausgefallene
Wochenaktualisierung, keine kaputten Daten.

**Wo man nachsieht:**

| | |
| --- | --- |
| `logs/cron-ts.log` | der ganze Lauf, inklusive `▶️ <notebook>` je Schritt |
| `logs/ts_run_latest.log` | Live-Mitschrift, aber **nur** von Schritt 1 (dem Tile-Abruf) |
| `logs/executed/` | die von nbconvert ausgeführten Notebook-Kopien, also die Zellausgaben von `xb_` |

Für `xb_` gibt es keine Live-Mitschrift: nbconvert schreibt Zellausgaben erst am Ende in
die Kopie unter `logs/executed/`. Während der Schritt läuft, sieht man in `cron-ts.log`
nur die `▶️`-Zeile.

---

## Gemeinsam genutzt

| | |
| --- | --- |
| [`cw_campaign.py`](cw_campaign.py) | die Logik beider Stränge, 48 Tests in [`test_cw_campaign.py`](test_cw_campaign.py) |
| `../utils/processed_osm_files/` | das Radwegnetz, erzeugt von [`../0_prepare_osm_network.ipynb`](../0_prepare_osm_network.ipynb), gelesen auch von der Marking-Kampagne |
| `../../output/mapillary_traffic-signs_DE-*.parquet` | Zeichen je Bundesland |
| `../utils/processed_motorways_germany_251215.parquet` | Autobahnen, ändert sich kaum |
| `../utils/config_mapillary_privat.json` | Mapillary-Token und MapRoulette-Key |

### Die Regel, die man leicht übersieht

`cw_campaign.py` wird **aus beiden Umgebungen importiert** — aus dem uv-Env von Strang A
und aus dem pip-Env des Worker-Images in Strang B.

> Jedes Paket, das `cw_campaign.py` importiert, muss in **beiden** Abhängigkeitslisten
> stehen, auf derselben Version.

Sonst läuft Strang A weiter und Strang B stirbt am Mittwochabend. Heute stimmen alle
gemeinsamen Pakete überein; festgehalten wird das von
`test_cw_campaign_laeuft_in_beiden_umgebungen`.

Der Test ist bewusst Wegwerfware: sobald das Repo auf ein einziges uv-Env umgestellt ist
(Schritt 4 in [`docs/plan_notebooks_zu_python.md`](../../docs/plan_notebooks_zu_python.md)),
ist die Invariante strukturell erfüllt und der Test kann weg.

---

## Bedienung

```bash
# Tests (ohne Netz, ~1 s)
cd use_cases/cycleway_complete_campaign
uv run --project .. pytest test_cw_campaign.py

# Strang A von Hand
uv run --project .. jupyter lab
```

Zugangsdaten kommen aus `../utils/config_mapillary_privat.json` oder, wenn gesetzt, aus
den Umgebungsvariablen `MAPILLARY_ACCESS_TOKEN` und `MAPROULETTE_API_KEY`.

## Was hier sonst noch liegt

| | |
| --- | --- |
| `blogpost.md` | Text zur Kampagne |
| `processed_osm_files/` | ältere OSM-Auszüge aus der Zeit vor dem gemeinsamen `0_`, nicht in git |
| `ts_output/` | Ausgabe von Strang B, nicht in git |
| `ts_output_ref/` | Referenzlauf von `x_` für die Gegenprobe in `xb_`, nicht in git |
