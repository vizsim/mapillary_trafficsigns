# `xb_` gegenüber `x_` — Gegenprobe und Umstiegsweg

**Stand:** 2026-09-20 · betrifft `xb_mapillary-trafficsigns_generateOutput_2radinfra.ipynb`
und `cw_campaign.py`

`x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb` **läuft unverändert weiter**.
Es ist in [`scripts/run_mapillary_notebooks.sh`](../../scripts/run_mapillary_notebooks.sh)
Teil der wöchentlichen ts-Pipeline (`2_get_mapillary_traffic_signs` → `x_…generateOutput`
→ `2_create_pmtiles`). `xb_` ist die Gegenprobe, nicht der Ersatz — bis der Vergleich
unten jemanden überzeugt.

---

## Ergebnis der Gegenprobe

Beide Notebooks auf derselben Eingabe (16 Bundesland-Parquets, Stand 15.09.2026):

```
  OK   sha256        (entpackte GeoJSON, 158.665 Features)
  OK   features
  OK   spalten
  OK   erste_id
  OK   letzte_id
  OK   README.md
  OK   signs_by_month.svg   (ohne Zeitstempel und clip-path-ids)
```

Die GeoJSON ist **byteweise identisch**. Verglichen wird der entpackte Inhalt, nicht die
`.gz`-Datei: im gzip-Header steckt ein Zeitstempel, zwei Läufe unterscheiden sich darin
immer.

---

## Die eine Falle, die wir uns eingefangen haben

Der erste Durchlauf war in allen Kennzahlen gleich — Featurezahl, Spalten, erste und
letzte id — und trotzdem wich der Hash ab. Bei 158.652 von 158.665 Features.

Die Ursache war die **Top-Level-`id` der GeoJSON-Features**. `GeoDataFrame.to_json()`
schreibt dort den DataFrame-Index:

```json
{ "type": "Feature", "id": "19", "properties": { "id": "502842277518482", … } }
```

`x_` filtert nacheinander (Zeitfilter, Autobahn-Filter) und lässt den Index dabei
lückenhaft: 0, 1, …, 13, 19, 20, … `xb_` hatte nach dem Filtern `reset_index(drop=True)`
stehen und damit dicht durchnummeriert. Inhaltlich dieselben Zeichen, andere Feature-ids.

Das ist **nicht** egal: tippecanoe übernimmt die Feature-id in die Vector Tiles, und
radinfra.de hängt daran. Ein stiller Umstieg hätte die ids aller Features verschoben.

Deshalb vergibt `filter_stable_signs` den Index jetzt bewusst nicht neu, und der
Autobahn-Filter in `xb_` auch nicht. Festgenagelt in
`test_filter_stable_signs_behaelt_den_index`.

> Für `1b_` ändert das nichts: dort steht die Mapillary-id als Spalte im Feature, der
> Index spielt keine Rolle. Nachgerechnet — `1b_` liefert danach dieselben 232 Aufgaben.

---

## Warum die SVG nie gleich sein wird

matplotlib schreibt in jede SVG einen `<dc:date>`-Zeitstempel und würfelt die
`clip-path`-ids pro Prozess neu (`svg.hashsalt`). Zwei Läufe **desselben** Notebooks
unterscheiden sich darin genauso. Die Vergleichszelle normiert beides weg; abgesehen
davon sind die Dateien Zeile für Zeile gleich.

---

## Was inhaltlich anders ist

| | `x_` | `xb_` |
| --- | --- | --- |
| Zeichentabelle | sieben Konstanten plus zwei Mapping-Dicts im Notebook | `cw_campaign.ZEICHEN`, geteilt mit `1b_` |
| Laden | Schleife über die Parquets im Notebook | `load_traffic_signs(columns=…, expect_files=…)` |
| Vollständigkeits-Guard | zwei `assert` im Notebook | `expect_files`, wirft `RuntimeError` |
| Autobahn-Ausschluss | gepufferter Zweitdatensatz + `mark_intersections` | `distance_to_nearest` |
| Hinweistexte | drei Zellen | `add_hinweis` |
| README | ~80 Zeilen im Notebook | `build_readme` |
| `import mapillary as mly` | vorhanden, **nie benutzt** | entfällt |
| Zellen | 30 | 10 Code-Zellen |

Der Zeitfilter (`last_seen_at > 2023-01-01`) und die Spaltenreihenfolge des Exports sind
unverändert. `EXPORT_SPALTEN` ist als Konstante festgenagelt, weil radinfra.de und das
pmtiles-Notebook daran hängen.

---

## Gegenprobe selbst fahren

```bash
cd use_cases/cycleway_complete_campaign

# 1. Referenzlauf mit x_
jupyter nbconvert --to notebook --execute x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb
cp -r ts_output ts_output_ref

# 2. xb_ laufen lassen - die letzte Zelle vergleicht gegen ts_output_ref
jupyter nbconvert --to notebook --execute xb_mapillary-trafficsigns_generateOutput_2radinfra.ipynb
```

`ts_output_ref/` steht in `.gitignore`.

Ohne `output/ml-ts_metadata.json` (die Datei entsteht auf dem Server) fällt das Datum in
der README auf „heute" zurück. Für den Vergleich ist das unkritisch, solange beide Läufe
am selben Tag stattfinden — auf dem Server ist die Datei da.

---

## Umstieg, wenn es soweit ist

Eine Zeile in [`scripts/run_mapillary_notebooks.sh`](../../scripts/run_mapillary_notebooks.sh):

```diff
-      "use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb"
+      "use_cases/cycleway_complete_campaign/xb_mapillary-trafficsigns_generateOutput_2radinfra.ipynb"
```

Mehr ist nicht nötig:

- Der Pfad steht nur dort. `COMMIT_PATHS` gibt es seit `c1c3f66` nicht mehr.
- `import cw_campaign` funktioniert im Container ohne `sys.path`-Anpassung: nbconvert
  setzt das Arbeitsverzeichnis auf das Notebook-Verzeichnis, und das Modul liegt
  daneben. Dass das so ist, beweist `x_` selbst — es liest `../../output/…`.
- Kein Image-Neubau. `cw_campaign` braucht nur geopandas/pandas/numpy/requests. Es
  *entfernt* sogar eine Abhängigkeit (`mapillary==1.0.15`), die in `requirements.txt`
  bleiben kann, solange andere Notebooks sie noch ziehen.

Klemmt der nächste Wochenlauf: Zeile zurück, `x_` läuft wieder.
