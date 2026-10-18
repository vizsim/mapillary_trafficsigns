# Maxspeed on main roads with accidents — traffic signs

**Last updated:** 2026-10-18

Finds sections of main road (trunk to tertiary) without `maxspeed` in OpenStreetMap that carry
a speed-limit sign detected by Mapillary, counts the accidents with injuries on each section from
the [Unfallatlas](https://data.vizsim.de/unfallorte/), and turns the sections with at least 4
accidents in 2020–2025 into tasks for MapRoulette. From 10 accidents a task has high priority.

| | |
| --- | --- |
| **Produces** | tasks for MapRoulette challenge [57279](https://maproulette.org/browse/challenges/57279) |
| **Triggered by** | a human, when a new round is due |
| **Runs in** | the repo's uv env (`uv sync` in the repo root); about 2 minutes and 7.5 GB RAM |
| **Needs** | the `osmium` CLI, a MapRoulette key, a Mapillary token |

The steps live in [`../campaign.py`](../campaign.py), shared with the other campaigns; what is
specific to this one — the sections, the assignment to roads, the accident data, the task text —
in [`../ms_campaign.py`](../ms_campaign.py). Tests are next to them in `../test_*.py`.

---

## Pipeline

```text
../0_prepare_osm_network.ipynb          ← shared with the other campaigns
    Geofabrik PBF → osmium tags-filter
    →  ../utils/processed_osm_files/processed_roads_germany_<date>.parquet   (every motor road, 4.1 M ways)

https://data.vizsim.de/unfallorte/       ← Unfallatlas 2016–2025, one GeoParquet
    →  ../utils/unfallorte/unfallorte_<years>_<date>.parquet               (checked against latest.json)

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-maxspeed_accidents.geojson   (MapRoulette fetches it from GitHub)
```

> **Mind `set_date`.** It appears in both notebooks and has to match. Geofabrik keeps daily
> extracts for only about 90 days.

## Selection

| Step | Setting |
| --- | --- |
| Signs | `regulatory--maximum-speed-limit-{30…130}--g1` (`ms.ZEICHEN`); 10 and 20 left out |
| Last seen | on 1 Jan 2025 or later |
| First to last sighting | at least 3 months |
| Clipped to | the German border |
| Dropped | signs within 30 m of a motorway, and within 30 m of a task of the Tempo-30 campaign (52985, any status, and its current GeoJSON) |
| Main road | `trunk`, `primary`, `secondary`, `tertiary` and their `_link` (`ms.HAUPTSTRASSEN`) |
| Without maxspeed | none of `maxspeed`, `maxspeed:forward`, `maxspeed:backward`; `maxspeed:type`, `source:maxspeed` or `zone:maxspeed` alone do not count |
| Section | connected ways without maxspeed with the same name, without a name the same `ref` (`ms.abschnitte`) |
| Sign or accident on a road | the nearest main road, at most 20 m (sign) or 15 m (accident) away, unless another road is more than 3 m closer (`ms.naechste_hauptstrasse`) |
| Accidents | Unfallatlas 2020–2025, every state in every year (`ms.load_unfaelle` refuses otherwise) |
| Task | a section with at least one sign and at least 4 accidents |
| Priority | High (`priority` 0) from 10 accidents, Medium (`priority` 1) from 4 |
| Task name | the smallest OSM way id of the section |
| Task geometry | the section as a line |

On the Mapillary data of 14.10.2026, the OSM extract of 17.10.2026 and the accident data of
03.10.2026 this gave **390 tasks**, 107 of them High. Of 254,537 km of main road, 60,665 km
(23.8 %) have no maxspeed; they carry 10.1 % of the accidents on main roads.

## Why it counts this way

Decided on 18.10.2026 after comparing the variants on the full data. The measure was: a missed
section is acceptable, a task that should not be one is not.

- **Per section, not per OSM way.** OSM cuts town roads into short pieces, and the piece with the
  sign rarely holds the accidents: on one Hauptstraße the sign stands on a 35 m piece without an
  accident, the section has 43. Counting per way mostly measures the length of the way — 2 % of
  the signs on ways under 100 m reached 4 accidents, 63 % of those on ways over 3 km.
- **Nearest road, not a buffer.** The accidents lie on the road axis already (60 % within 1 m,
  95 % within 5 m of a road), so the width of a buffer hardly matters. A buffer counts an accident
  at a junction once for every way that meets there — 1.5 times on average with 5 m, 1.9 times
  with 10 m — and adds the accidents of a parallel way or a side street. It only ever adds tasks:
  counted per section, a 10 m buffer took 1,241 more sign groups over the threshold, nearest
  assignment 2.
- **Only 2020–2025.** The states joined the Unfallatlas between 2016 and 2020; with all years,
  Bavaria and Baden-Württemberg would count four years more than NRW.
- **At least 3 months between first and last sighting.** At main roads that already have a
  maxspeed, the sign value matched it in 61 % of the signs seen in a single month, in 73 % of
  those seen over at least 3 months. The distance to the nearest side street made no difference,
  and neither did the direction a sign faces (`aligned_direction` from the Graph API).

About a quarter of the signs does not match the maxspeed even with these filters. Part of that is
no false alarm here: the sign starts the next section, or OSM lacks a night limit (30 at a road
with 50 is the most frequent mismatch). The share of "Not an Issue" and "Too Hard" after the
first round tells how high the real rate is — and whether the next round should take the signs
seen only once.

Long sections are tasks too: 90 % are up to 4.7 km, the longest is the L 267 with 11.5 km.
The task text asks to fill in the whole section, also the parts without a sign.

## The challenge

[57279](https://maproulette.org/browse/challenges/57279), created on 18.10.2026 in project 60811.
Its settings, as the other challenges have them:

| Field | Value |
| --- | --- |
| Source | GeoJSON by URL: `https://raw.githubusercontent.com/vizsim/mapillary_trafficsigns/refs/heads/main/use_cases/maxspeed_accidents_campaign/maproulette_tasks_missing-maxspeed_accidents.geojson` |
| Description | the block at the end of the notebook |
| Detailed instructions for mappers | `{{instruction}}` and nothing else — inside a code fence MapRoulette shows the task text as source instead of formatted text, as it did at first |
| Priority rules | High: `priority` == 0, Medium: `priority` == 1 (integer) |
| Changeset comment | `#missing-maxspeed_mapillary-signs #maproulette` |

A new round: run the notebook, commit and push the GeoJSON, then "Rebuild tasks". Uploading
through the API is built in, but waits for MapRoulette — see the
[pedestrian-crossing README](../pedestrian_crossing_campaign/README.md#uploading-through-the-api).
To rebuild the extract first, run `../0_prepare_osm_network.ipynb` with `OSM_EXTRACTS=roads`.

## Accident data

Unfallatlas, © Statistische Ämter des Bundes und der Länder, Datenlizenz Deutschland –
Namensnennung – Version 2.0 ([dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0)),
[unfallatlas.statistikportal.de](https://unfallatlas.statistikportal.de/). Prepared by vizsim
(merged and harmonised), [data.vizsim.de/unfallorte](https://data.vizsim.de/unfallorte/); counted
per road section here. The data only orders and selects the tasks; nothing of it goes into
OpenStreetMap.
