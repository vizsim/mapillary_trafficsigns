# `xb_` gegenüber `x_` — Marking-Kampagne

**Stand:** 2026-09-20 · betrifft `xb_mapillary-markings_generateOutput_2radinfra.ipynb`
und [`../cw_campaign.py`](../cw_campaign.py)

Seit dem 20.09.2026 führt die wöchentliche mk-Pipeline (donnerstags 01:00 UTC)
`xb_` aus. `x_mapillary-markings_generateOutput_2radinfra.ipynb` bleibt unverändert
daneben liegen, bis `xb_` ein paar Wochen sauber gelaufen ist — zurückschalten heißt:
in [`scripts/run_mapillary_notebooks.sh`](../../scripts/run_mapillary_notebooks.sh)
wieder `x_` eintragen.

Das Vorbild ist die Verkehrszeichen-Kampagne, die den Umstieg am 20.09.2026 gemacht hat:
[`../cycleway_complete_campaign/xb_unterschiede.md`](../cycleway_complete_campaign/xb_unterschiede.md).

---

## Ergebnis der Gegenprobe

Beide Notebooks auf derselben Eingabe (16 Bundesland-Parquets, Stand 17.09.2026):

```text
  OK   sha256        (entpackte GeoJSON, 35.250 Features)
  OK   features
  OK   spalten
  OK   erste_id
  OK   letzte_id
  OK   README.md
  OK   markings_by_month.svg   (ohne Zeitstempel und clip-path-ids)
```

Die GeoJSON ist **byteweise identisch**. Verglichen wird der entpackte Inhalt: im
gzip-Header steckt ein Zeitstempel, zwei Läufe unterscheiden sich darin immer.

---

## Zwei Fallen auf dem Weg

### 1 · Wann gefiltert wird, bestimmt die Feature-ids

`GeoDataFrame.to_json()` schreibt den DataFrame-Index als Top-Level-`id` der Features,
und tippecanoe trägt die in die Vector Tiles. `x_` filtert **beim Lesen, je Datei**
(Klasse und Zeitraum), fügt erst danach zusammen und vergibt dabei einen dichten Index.
Wer stattdessen erst zusammenfügt und dann filtert, bekommt dieselben Zeilen mit anderen
ids — bei gleicher Anzahl, gleichen Spalten und gleichen Mapillary-ids also eine
Abweichung, die keine Kennzahl zeigt.

Deshalb nimmt `load_features` jetzt `seen_after` und `first_seen_after` entgegen und
filtert damit vor dem Zusammenfügen. Dasselbe gilt für `clip_to_boundary` und
`filter_by_days_seen`: beide vergeben den Index bewusst nicht neu.

Festgehalten in `test_load_features_filtert_beim_lesen_und_praegt_den_index` und
`test_clip_to_boundary_behaelt_den_index`.

> Dieselbe Falle hatte schon die Verkehrszeichen-Kampagne — dort über ein
> `reset_index(drop=True)` nach dem Autobahn-Filter.

### 2 · Die Grafik muss wirklich dieselbe sein

Der erste Durchlauf war in GeoJSON und README identisch, nur die SVG wich ab — 2.623
gegen 2.188 Zeilen. Zwei Ursachen, beide in meinem neu geschriebenen Plot-Code: ein
anderer Titel, und die **Zahlen über den Balken** hatte ich weggelassen. Nach dem
Angleichen stimmt auch die SVG.

Was nie gleich sein wird: matplotlib schreibt einen `<dc:date>`-Zeitstempel und würfelt
die `clip-path`-ids pro Prozess neu. Zwei Läufe **desselben** Notebooks unterscheiden
sich darin genauso; die Vergleichszelle normiert beides weg.

---

## Was inhaltlich anders ist

| | `x_` | `xb_` |
| --- | --- | --- |
| Laden | Schleife über die Parquets im Notebook | `load_features(prefix=…, seen_after=…)` |
| Vollständigkeits-Guard | seit 20.09. zwei `assert` im Notebook | `expect_files`, wirft `RuntimeError` |
| Grenzverschnitt | sjoin im Notebook | `clip_to_boundary` |
| Standzeit-Filter | `delta_days_seen > 180` im Notebook | `filter_by_days_seen` |
| Export | `to_json` + gzip im Notebook | `write_geojson_gz` (unter `.tmp`, dann umbenannt) |
| id-Regressionscheck | 20 Zeilen im Notebook | `assert_ids_are_strings` |
| README | ~60 Zeilen im Notebook | `build_readme_markierungen` |
| `import mapillary as mly` | vorhanden, **nie benutzt** | entfällt |
| Zellen | 32 | 9 Code-Zellen |

### Kein `sync_features` — und warum das wichtig ist

Beim Bau hatte ich das Sync-Muster aus den `1b_`-Notebooks übernommen. Für ein Notebook,
das auf dem Server läuft, ist das nicht nur überflüssig, sondern schädlich: dort
**entstehen** die Parquets in Schritt 1 derselben Pipeline und werden erst danach nach B2
geladen. Die Last-Modified der veröffentlichten Kopie ist damit immer jünger als die
lokale Datei — `sync_features` würde also jede Woche die frisch geholten Daten durch die
Vorwochen-Fassung ersetzen. Die Zelle ist wieder raus.

Für die `1b_`-Notebooks bleibt der Sync richtig: die laufen von Hand auf einem Rechner,
der die Daten nicht selbst erzeugt.

Unverändert bleiben die Filterwerte (`last_seen_at > 2023-01-01`, `first_seen_at >
2000-01-01`, mehr als 180 Tage Standzeit) und `EXPORT_SPALTEN_MARKIERUNGEN`.

### Eine Unschönheit, die bewusst bleibt

Die README nennt den Erfassungszeitraum als `2014-03-30 00:00:00 - 2026-09-15 00:00:00`.
Die `00:00:00` sind ein Artefakt: `x_` führt die Datumsspalten an dieser Stelle als
`datetime`. `xb_` reproduziert das absichtlich, damit die Gegenprobe greift. Nach dem
Umstieg ist das eine Zeile im Notebook.

---

## Gegenprobe selbst fahren

```bash
cd use_cases/cycleway_complete_marking_campaign

# 1. Referenzlauf mit x_
jupyter nbconvert --to notebook --execute x_mapillary-markings_generateOutput_2radinfra.ipynb
cp -r mk_output mk_output_ref

# 2. xb_ laufen lassen - die letzte Zelle vergleicht gegen mk_output_ref
jupyter nbconvert --to notebook --execute xb_mapillary-markings_generateOutput_2radinfra.ipynb
```

`mk_output_ref/` steht in `.gitignore`.

---

## Umstieg am 20.09.2026

Eine Zeile in [`scripts/run_mapillary_notebooks.sh`](../../scripts/run_mapillary_notebooks.sh),
im `mk)`-Zweig:

```diff
-      "use_cases/cycleway_complete_marking_campaign/x_mapillary-markings_generateOutput_2radinfra.ipynb"
+      "use_cases/cycleway_complete_marking_campaign/xb_mapillary-markings_generateOutput_2radinfra.ipynb"
```

Mehr war nicht nötig — dieselben Voraussetzungen wie bei ts, dort am selben Tag in
Produktion bestätigt: der Pfad steht nur an dieser Stelle, `import cw_campaign`
funktioniert im Container über `sys.path.insert(0, "..")`, und es braucht keinen
Image-Neubau.

**Rückweg:** Zeile zurück auf `x_`, pushen, auf dem Server ziehen. Scheitert das
Notebook im Wochenlauf, bricht `run_worker_with_vpn.sh` **vor** dem B2-Upload ab — der
Schaden ist eine ausgefallene Wochenaktualisierung, keine kaputten Daten.
