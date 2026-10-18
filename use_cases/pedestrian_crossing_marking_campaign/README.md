# Pedestrian crossing campaign — road markings

**Last updated:** 2026-10-18

> **Archived.** Challenge 53697 stays archived: the zebra detections of Mapillary produce too
> many false positives for a challenge. The code is kept up to date with the twin, so a new
> round is a run of the notebook away if the detections get better.

The twin of [`../pedestrian_crossing_campaign/`](../pedestrian_crossing_campaign/README.md):
same check, same distances, same module. The difference is what the detections are:
**zebra crossings painted on the road** (`marking--discrete--crosswalk-zebra`, a Mapillary
map feature point), not DE:350 signs.

| | |
| --- | --- |
| **Produces** | tasks for MapRoulette challenge 53697 (archived) |
| **Triggered by** | a human, when a new round is due |
| **Runs in** | the repo's uv env (`uv sync` in the repo root) |
| **Needs** | the `osmium` CLI, a Mapillary token |

The steps live in [`../campaign.py`](../campaign.py); the classes, distances and task texts of
both pedestrian-crossing campaigns in [`../pc_campaign.py`](../pc_campaign.py).

```text
../0_prepare_osm_network.ipynb          ← shared with the other campaigns
    →  ../utils/processed_osm_files/processed_crossings_germany_<date>.parquet

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-ped-crossing_map-feature-point.geojson   (MapRoulette fetches it from GitHub)
```

A new round: run the notebook, commit and push the GeoJSON, then "Rebuild tasks" in
MapRoulette. Running it unattended and uploading through the API work as described in the
[twin's README](../pedestrian_crossing_campaign/README.md#running-it-unattended).

## Selection

As in the twin — no `highway=crossing` within 50 m, markings up to 100 m apart become one
task, closed tasks block within 50 m — with these settings of its own:

| | |
| --- | --- |
| Dataset | `campaign.PREFIX_MARKIERUNGEN` (map feature points) |
| Class | `marking--discrete--crosswalk-zebra` |
| Last seen after | `2025-01-01` |
| First to last sighting | at least 12 months |
| Task text | `pc.aufgabe_markierung` |

On the Mapillary data of 15.10.2026 and the OSM extract of 17.10.2026 this gave 465 tasks, in
the file in this folder. They are not in the challenge: it stays archived (see above). Were it
rebuilt, 39 of its open tasks would be refreshed, 426 added, and "remove unmatched" would clear
the 22 open ones of the 2025 round that are no longer in the file.

## What changed from the 2025 round

On the same data and without the border clip, the old notebook and this one pick the same
markings, before and after grouping (2,748 and 1,120). The differences:

- **Clipped to Germany.** One in eight zebra detections lies across the border, where the
  OSM extract has no crossings. Without the clip there would be 1,120 candidates instead of 472.
- **Newest image** from the Graph API instead of geo searches with the camera heading.
- **Existing tasks** of challenge 53697 are taken into account; the old notebook had a
  placeholder for the challenge id.
- **OSM extract** from the shared notebook instead of a copy of its own from 11/2025.
- **Task text** laid out like the twin's, with the distance to the nearest mapped crossing and
  the tags to copy.
