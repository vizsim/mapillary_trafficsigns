# `1b_` gegenüber `1_` — was anders ist und warum

**Stand:** 2026-09-20 · betrifft `1b_merge_mapillary-trafficsigns_osm-cycleways.ipynb`
und `../cw_campaign.py`

`1_merge_mapillary-trafficsigns_osm-cycleways.ipynb` bleibt unverändert liegen.
`1b_` ist eine zweite Fassung mit derselben Aufgabe: aus Mapillary-Verkehrszeichen
MapRoulette-Aufgaben für fehlende Radinfrastruktur bauen. Die Rechenschritte liegen in
[`../cw_campaign.py`](../cw_campaign.py) und sind mit `pytest test_cw_campaign.py` in
`use_cases/` prüfbar (49 Tests, ohne Netz).

---

## Das Ergebnis im Vergleich

Beide Fassungen auf dem Datenstand vom 15.09.2026, OSM-Extrakt `260915`:

| Schritt | `1_` | `1b_` |
| --- | ---: | ---: |
| Zeichen nach Zuschnitt auf Deutschland | 252.960 | 252.960 |
| zuletzt gesehen nach 2025-07-01 | 63.733 | 63.733 |
| davon ≥ 9 Monate Standzeit | 25.726 | 25.726 |
| OSM-Wege mit Radinfra | 822.733 | 822.745 |
| keine Radinfra in 30 m | 411 | 411 |
| Kandidaten (Prio 0) | 256 | 256 |
| Kandidaten (Prio 1) | 56 | 56 |
| **Aufgaben nach Abzug der Challenge** | **234** | **232** |
| davon mit anderem Bild als in `1_` | — | **206** |

Die Zwischenstände stimmen überein. Die Differenz von 2 Aufgaben am Ende kommt nicht
aus der Rechnung, sondern aus der Challenge: zum Zeitpunkt des `1b_`-Laufs blockierten
168 bestehende Aufgaben (80 Kandidaten fielen weg), beim `1_`-Lauf waren es 78.

Der Unterschied, um den es geht, steht in der letzten Zeile: **206 von 232 Aufgaben
verlinken jetzt ein anderes Foto.**

---

## 1 · Das verlinkte Bild ist jetzt das neueste

Der eigentliche Anlass für `1b_`.

`1_` holte pro Zeichen das Feature über die `mapillary`-Library und nahm:

```python
images = feature["features"]["properties"]["images"]["data"]
return str(images[-1]["id"]) if images else None
```

`images[-1]` ist das letzte Element einer Liste, die **nicht nach Aufnahmezeit sortiert
ist**. Die Reihenfolge wechselt sogar zwischen zwei Abfragen desselben Features mit
unterschiedlicher Feldsyntax. Der Instruction-Text in `1_` trug dem Rechnung:

> (Hinweis: Das zuerst angezeigte Bild ist wahrscheinlich nicht das neueste …)

**Gemessen** an 600 Radwegzeichen in Bremen, wie weit das gewählte Bild vom neuesten
verfügbaren entfernt lag:

| | Anteil |
| --- | ---: |
| `images[-1]` ≠ neuestes Bild | 84 % |
| mehr als 30 Tage älter | 21 % |
| mehr als 1 Jahr älter | 10 % |
| mehr als 2 Jahre älter | 4 % |
| 99. Perzentil des Abstands | 2.511 Tage |

Der Median liegt bei 0 Tagen — meistens passt es zufällig. Aber jede fünfte Aufgabe
verlinkte ein spürbar veraltetes Foto, und im Extremfall eines von 2016 für ein Zeichen,
das zuletzt 2026 gesehen wurde.

### Die Lösung

Die Graph-API beherrscht Feldexpansion — das steht so nicht in der Mapillary-Doku:

```http
GET https://graph.mapillary.com/{id}?fields=id,images{id,captured_at}
```

Damit kommt die Aufnahmezeit mit, und die Auswahl ist eine Zeile
(`cw_campaign.newest_image_ids`):

```python
neuestes = max(bilder, key=lambda bild: bild["captured_at"])
```

**Kein Zielkonflikt mit der Sichtbarkeit.** Die naheliegende Sorge wäre, dass das neueste
Bild aus größerer Entfernung aufgenommen wurde und das Zeichen darauf nur ein Fleck ist.
Das Gegenteil ist der Fall — medianer Abstand Kamera ↔ Zeichen an 200 Stichproben:

| | Median | p90 |
| --- | ---: | ---: |
| bisher gewähltes Bild | 28,3 m | 59,6 m |
| neuestes Bild | **19,8 m** | 56,1 m |

Deshalb wählt `newest_image_ids` schlicht das neueste, ohne Abstandsfilter.

### Gegenprobe im Notebook

`last_seen_at` aus dem Parquet ist die letzte Aufnahme, auf der das Zeichen erkannt
wurde. Stimmt die Bildauswahl, muss das verlinkte Bild von diesem Tag sein. Im Lauf vom
20.09.2026: **224 von 232** Bildern am selben Tag.

### Was offen bleibt

Bei **5 von 232** Aufgaben ist das neueste Bild aus der `images`-Kante älter als das
`last_seen_at` des Parquets — im schlimmsten Fall um 3.768 Tage. Bei genau diesen
Features liefert die API auch ihr eigenes `last_seen_at`-Feld nicht. Die Kante enthält
das Bild, auf das sich `last_seen_at` stützt, schlicht nicht; etwas Besseres ist daraus
nicht zu wählen. Drei weitere Bilder sind bis zu 65 Tage **neuer** als `last_seen_at` —
das ist erwartbar, das Parquet stammt aus einem früheren Durchlauf.

Bleiben mehr als 5 % der Features ohne Bild, bricht `newest_image_ids` ab, statt ein
Teilergebnis zurückzugeben: Aufgaben ohne Foto sehen in MapRoulette genauso plausibel
aus wie vollständige.

---

## 2 · Sammelabfragen statt Einzelabrufe

`?ids=a,b,c` fragt bis zu 50 Features in einem Request ab. Gemessen an 200 Features:

| Verfahren | Dauer | Durchsatz |
| --- | ---: | ---: |
| einzeln, 5 Threads (wie `1_`) | 30,5 s | 6,6 /s |
| einzeln, 10 Threads | 7,4 s | 26,9 /s |
| **Sammelabfrage à 50, 8 Threads** | **1,9 s** | **105,7 /s** |

Im echten Lauf: 232 Features in 5,2 s statt 1:14 min.

Nebeneffekt: die `mapillary`-Library wird nicht mehr gebraucht, und mit ihr entfallen der
`suppress_stdout`-Kontextmanager und das Zurücksetzen aller Logger — beides stand in `1_`
nur da, um die Library ruhigzustellen.

---

## 3 · Eine Abstandsspalte statt zweier Pufferläufe

`1_` baute zwei gepufferte Kopien des Datensatzes (25 m und 30 m), verschnitt beide
getrennt mit dem Radwegnetz und setzte sie danach wieder zusammen:

```python
df_buffered_both_false = pd.concat([df_buffered_30_false, df_buffered_25_false]) \
    .sort_values("buffer_size").drop_duplicates(subset=["id"], keep="last")
```

Das ist eine umständliche Schreibweise für eine Distanzklassifikation: wer keine Radinfra
in 30 m hat, hat auch keine in 25 m. `1b_` rechnet einmal den Abstand
(`cw_campaign.distance_to_nearest`) und leitet die Priorität daraus ab
(`assign_priority`, Schwellen in `PRIO_AB_DISTANZ`).

Das Verfahren bleibt schnell, weil die 5,8 Mio. OSM-Linien **nicht** umprojiziert werden:
ein Puffer um die paar tausend Punkte wandert ins CRS der Linien, und nur die Treffer
dieses Vorfilters werden metrisch nachgemessen. 25.726 Zeichen gegen 822.745 Wege: 4,9 s.

Zwei Nebenwirkungen:

- **Die Aufgabentexte nennen den echten Abstand** („ca. 27 m") statt einer Schwelle
  („mind. 25 Meter").
- **Eine fragile Stelle fällt weg.** In `1_` mischte die Auswahl Masken aus zwei
  verschiedenen DataFrames:

  ```python
  df_buffered_25[(df_buffered_25.has_cw_intersection == False)
                 & (df_buffered_30.has_mw_intersection == False)]
  ```

  Das lieferte nur deshalb das Richtige, weil beide Frames denselben Index geerbt hatten.

Weitere Schwellen sind jetzt eine Zeile in `PRIO_AB_DISTANZ` — etwa eine dritte Stufe
„Prio 2 ab 20 m", ohne einen dritten Pufferlauf.

---

## 4 · `sidewalk:bicycle` zählt als Radinfra

Der TODO-Kommentar aus `1_`, Zelle 5:

```python
# (cycleways["sidewalk_bicycle"].isin(["designated"])) |  TODO: add "sidewalk:bicycle" in ini file
```

Die Spalte liegt inzwischen im Parquet — das Notebook `0_prepare_…` schreibt sie, der
Filter las sie nur nicht. Wirkung bundesweit: **12 zusätzliche Wege** (822.733 → 822.745),
am Ergebnis dieses Laufs ändert sich nichts. `filter_cycle_infrastructure` überspringt
Spalten, die nicht im Parquet stehen, statt mit `KeyError` abzubrechen, und schreibt beim
Aufruf hin, welche Tags es tatsächlich genutzt hat.

---

## 5 · Kleinere Aufräumarbeiten

| Stelle | `1_` | `1b_` |
| --- | --- | --- |
| Standzeit in Monaten | `apply(axis=1)` mit `strptime` pro Zeile | vektorisiert über `dt.year` / `dt.month` |
| Einlesen der Parquets | erst alle 16 Länder komplett, dann filtern | pro Datei filtern, dann zusammenfügen |
| Bild-IDs | teils `float64`, hinterher per `Decimal` repariert | durchgehend `str` |
| Geometrie am Ende | Puffer → `centroid` in EPSG:25832 (Puffer waren 25833) | Punktgeometrie bleibt durchgehend erhalten |
| Ausgabedatei | direktes `open()` + `json.dump` | unter `.tmp` schreiben, dann umbenennen |
| Zellen im Notebook | 68, davon 14 leer oder auskommentiert | 13 Code-Zellen |

---

## Bekannte Abweichung im Verhalten

`drop_near_existing_tasks` nutzt für **alle** Zeichen denselben Radius (30 m) gegen die
bestehenden Challenge-Aufgaben. `1_` verschnitt dort den jeweiligen Puffer des Zeichens,
also 25 m oder 30 m. Der größere Radius entfernt im Zweifel eine Aufgabe zu viel statt
eine doppelt anzulegen. Anpassbar über das Argument `radius_m`.

---

## Bedienung

```bash
cd use_cases/cycleway_complete_campaign

# Tests (ohne Netz, ~1 s)
uv run pytest test_cw_campaign.py   # in use_cases/

# Notebook
uv run --project .. jupyter lab 1b_merge_mapillary-trafficsigns_osm-cycleways.ipynb
```

Zugangsdaten kommen aus `../utils/config_mapillary_privat.json` oder, wenn gesetzt, aus
`MAPILLARY_ACCESS_TOKEN` bzw. `MAPROULETTE_API_KEY`.

### Die Ausgabedatei behält ihren Namen

Das Notebook schreibt in dieselbe Datei wie `1_`,
`maproulette_tasks_missing-cw_instruction_vz_name_new.geojson`, weil MapRoulette einen
festen Eingabepfad braucht. Jeder Lauf überschreibt sie also.

Damit die letzte Zelle trotzdem etwas zu vergleichen hat, liest das Notebook den
bisherigen Inhalt **vor** dem Schreiben ein (`read_geojson` → `vorheriger_stand`) und
stellt ihn danach dem neuen Lauf gegenüber. Wer den alten Stand zurückbraucht, holt ihn
aus der git-History — die Datei ist getrackt, `git diff` zeigt die Änderung zeilenweise.
