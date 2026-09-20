# `1b_` gegenüber `1_` — Marking-Kampagne

**Stand:** 2026-09-20 · betrifft `1b_merge_mapillary-markings_osm-cycleways.ipynb`
und [`../cw_campaign.py`](../cw_campaign.py)

`1_merge_mapillary-markings_osm-cycleways.ipynb` bleibt unverändert liegen. `1b_` macht
dasselbe — aus erkannten Fahrrad-Symbolen auf der Fahrbahn MapRoulette-Aufgaben für
Challenge 53882 bauen — nutzt dafür aber dasselbe Modul wie die Verkehrszeichen-Kampagne.
Aufbau und Aufteilung sind identisch zum Zwilling
[`../cycleway_complete_campaign/1b_merge_mapillary-trafficsigns_osm-cycleways.ipynb`](../cycleway_complete_campaign/1b_merge_mapillary-trafficsigns_osm-cycleways.ipynb).

Tests: `pytest test_cw_campaign.py` in `use_cases/` (49, ohne Netz).

---

## Das Ergebnis im Vergleich

| | `1_` (committet) | `1b_` |
| --- | ---: | ---: |
| Datenstand der Markierungen | 01.07.2026 | **17.09.2026** |
| Markierungen nach Zuschnitt auf Deutschland | — | 152.474 |
| zuletzt gesehen nach 2025-01-01 | — | 77.446 |
| davon ≥ 9 Monate Standzeit | — | 24.788 |
| keine Radinfra in 30 m | — | 561 |
| Kandidaten | — | 634 |
| **Aufgaben nach Abzug der Challenge** | **483** | **593** |
| davon mit anderem Bild | — | **364** von 400 gemeinsamen |

Die Mengen sind nicht direkt vergleichbar: die committete Datei stammt von einem Lauf auf
elf Wochen älteren Daten. Was zählt, ist die letzte Zeile — von den 400 Aufgaben, die in
beiden Ständen vorkommen, verlinken **364 jetzt ein anderes Foto**.

---

## 1 · Das verlinkte Bild ist das neueste

Wie in der Verkehrszeichen-Kampagne nahm `1_` das letzte Element einer unsortierten
Liste:

```python
return str(images[-1]["id"]) if images else None
```

Gemessen an 600 Stichproben war das in 84 % der Fälle nicht das neueste Bild, in 21 % lag
mehr als ein Monat dazwischen, in 10 % mehr als ein Jahr. Die Begründung und die
Messreihe stehen ausführlich in
[`../cycleway_complete_campaign/1b_unterschiede.md`](../cycleway_complete_campaign/1b_unterschiede.md).

**Gegenprobe im Lauf vom 20.09.2026: 581 von 593** Bildern stammen vom selben Tag wie
`last_seen_at`.

> Derselbe Lauf auf den alten lokalen Parquets (01.07.) kam nur auf 330 von 425. Das ist
> kein Fehler der Bildauswahl, sondern ihr Gegenteil: Mapillary hatte seit Juli neuere
> Aufnahmen, von denen das alte Parquet nichts wusste. Genau deshalb hat `1b_` jetzt
> einen Sync-Schritt.

---

## 2 · Der Challenge-Abzug wirkt jetzt wirklich

Das ist der Fund, der über das Übliche hinausgeht. `1_` rechnet in Zelle 47 den Abzug der
bestehenden Challenge-Aufgaben aus — und wirft ihn in Zelle 50 weg:

```python
df_process_img = df_buffered_both_false.copy()
#df_process_img = df_buffered_both_false_no_challenge.copy()    # <- die bereinigte Fassung
```

Dadurch tauchten Stellen, die in MapRoulette bereits als *Not an issue* oder *Already
fixed* abgehakt waren, in der nächsten Runde erneut als Aufgabe auf. Im aktuellen Lauf
betrifft das **41 von 634** Kandidaten.

Die Verkehrszeichen-Kampagne hatte diesen Fehler nicht — dort wird die bereinigte Fassung
verwendet.

---

## 3 · Daten werden geholt, nicht vorausgesetzt

`1_` las, was zufällig in `output/` lag. Beim Bau dieses Notebooks waren das Parquets vom
**01.07.**, während der Server den **17.09.** hatte — elf Wochen, ohne jeden Hinweis im
Notebook.

`1b_` ruft `cw.sync_features(ordner_punkte, prefix=cw.PREFIX_MARKIERUNGEN)` und lädt, was
lokal fehlt oder auf dem Server neuer ist. Dazu der **Vollständigkeits-Guard**: fehlt ein
Bundesland-Parquet, bricht der Lauf ab, statt still eine Teilmenge zu verarbeiten.

---

## 4 · Eine Abstandsspalte statt zweier Pufferläufe

`1_` baute zwei gepufferte Kopien (25 m und 30 m), verschnitt beide getrennt und setzte
sie per `concat` + `sort_values` + `drop_duplicates` wieder zusammen. `1b_` rechnet einmal
den Abstand (`distance_to_nearest`) und leitet die Priorität daraus ab
(`assign_priority`). Die Aufgabentexte nennen dadurch den gemessenen Abstand
(„ca. 29 m") statt der Schwelle („mind. 25 Meter").

Einen Autobahn-Filter gibt es hier weiterhin nicht — er war in `1_` durchgehend
auskommentiert. Fahrbahnmarkierungen werden an Autobahnen praktisch nicht erkannt.

---

## 5 · Was die Kampagne vom Zwilling unterscheidet

Beide Notebooks rufen dasselbe Modul, aber mit anderen Einstellungen:

| | Verkehrszeichen | Markierungen |
| --- | --- | --- |
| Datensatz | `PREFIX_ZEICHEN` | `PREFIX_MARKIERUNGEN` |
| Klassen | 4 Verkehrszeichen | 1 Markierung (Fahrrad-Symbol) |
| Zeitfilter | `> 2025-07-01` | `> 2025-01-01` |
| Radinfra zählt bei | `designated` | `designated`, **`yes`** |
| Autobahn-Ausschluss | ja | nein |
| Challenge | 52916 | 53882 |
| Aufgabentext | `aufgabe_verkehrszeichen` | `aufgabe_markierung` |

Das `yes` macht einen großen Unterschied: **1.444.646 statt 822.745** Wege gelten damit
als Radinfrastruktur. Gewollt — eine Fahrbahnmarkierung liegt oft auf einem Weg, der für
Radverkehr nur freigegeben, nicht angeordnet ist.

`aufgabe_markierung` hebt in Mapillary das Symbol hervor (`mapFeature[]=` statt
`trafficSign[]=`), blendet in TILDA beide Ebenen ein und hängt die Kopiervorlagen für
Schutzstreifen, Radfahrstreifen und Piktogrammketten an.

---

## 6 · Kleineres

| Stelle | `1_` | `1b_` |
| --- | --- | --- |
| Bild-Abruf | `mly.interface.feature_from_key` je Feature, 5 Threads | Sammelabfrage à 50 über die Graph-API |
| Standzeit in Monaten | `apply(axis=1)` mit `strptime` pro Zeile | vektorisiert |
| Bild-IDs | teils `float64`, per `Decimal` repariert | durchgehend `str` |
| Geometrie am Ende | Puffer → `centroid` in EPSG:25832 | Punktgeometrie bleibt erhalten |
| Ausgabedatei | direktes `open()` | unter `.tmp` schreiben, dann umbenennen |
| `sidewalk:bicycle` | TODO-Kommentar, ungenutzt | zählt mit (seit dem gemeinsamen `0_`) |
| Zellen | 70 | 12 Code-Zellen |

---

## Bedienung

```bash
cd use_cases

uv run pytest test_cw_campaign.py
uv run jupyter lab
```

Das Notebook schreibt nach `maproulette_tasks_missing-cw_markings.geojson` — derselbe
Name wie bisher, damit MapRoulette seinen Eingabepfad behält. Den vorherigen Inhalt liest
es **vor** dem Überschreiben ein, damit die letzte Zelle etwas zu vergleichen hat.
