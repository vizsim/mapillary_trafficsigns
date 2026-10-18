# Pedestrian crossing campaign — traffic signs

**Last updated:** 2026-10-18

Finds pedestrian-crossing signs (DE:350) detected by Mapillary where OpenStreetMap has no
`highway=crossing` within 50 m, and turns them into tasks for MapRoulette. Built like the
`maproulette_*` pipeline of the [cycleway campaigns](../cycleway_complete_campaign/README.md);
there is no weekly export here.

| | |
| --- | --- |
| **Produces** | tasks for MapRoulette challenge 53589 (completed in 2025) |
| **Triggered by** | a human, when a new round is due |
| **Runs in** | the repo's uv env (`uv sync` in the repo root), locally or on the server |
| **Needs** | the `osmium` CLI, a MapRoulette key, a Mapillary token |

The steps live in [`../campaign.py`](../campaign.py), shared with the cycleway campaigns;
what is specific to this one — the sign, the distances, the task text — in
[`../pc_campaign.py`](../pc_campaign.py). Tests are next to them in `../test_*.py`.

---

## Pipeline

```text
../0_prepare_osm_network.ipynb          ← shared with the cycleway campaigns
    Geofabrik PBF → osmium tags-filter n/highway=crossing
    →  ../utils/processed_osm_files/processed_crossings_germany_<date>.parquet

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-ped-crossing.geojson
```

> **Mind `set_date`.** It appears in both notebooks and has to match. Geofabrik keeps daily
> extracts for only about 90 days.

The output keeps its name on every run, because MapRoulette needs a stable path. The last
cell of the notebook compares the new tasks with the file in the repo.

## Selection

| Step | Setting |
| --- | --- |
| Sign | `information--pedestrians-crossing--g1` (DE:350) |
| Last seen after | `2025-01-01` |
| First to last sighting | at least 12 months |
| Clipped to | the German border |
| No `highway=crossing` within | 50 m (`pc.SUCHRADIUS_M`) |
| Signs that become one task | up to 100 m apart (`pc.ZUSAMMENFASSEN_M`); the one seen last stays |
| Existing tasks that block | all but Fixed, Created and Skipped, within 50 m |

Run on the data of 14.10.2026, this gave 190 tasks.

## What changed from the 2025 rounds

On the same data and without the border clip, the old notebook and this one pick the same
signs, before and after grouping. The differences:

- **Clipped to Germany.** The parquets are cut along zoom-14 tiles, so border tiles reach
  abroad, where the OSM extract has no crossings. Without the clip, the 14.10.2026 data gave
  550 candidates instead of 204.
- **Newest image** from the Graph API, which lists the images a sign was detected in. The old
  notebook searched by location and camera heading, with several requests per sign.
- **Fixed tasks no longer block**, as in the cycleway campaigns.
- **OSM extract** from the shared notebook, without the Conda environment; the crossing tags
  are columns instead of one `other_tags` string.
- **Task text** laid out like the cycleway tasks, with the distance to the nearest mapped
  crossing, a Traffic Sign Tool link and the tags to copy.

---

## Running it unattended

Both notebooks run unchanged under `jupyter nbconvert --execute`. A run on the server must
not touch tracked files — the deploy step refuses to update a server with local changes — so
it sets these instead:

| Variable | Notebook | Effect |
| --- | --- | --- |
| `OSM_EXTRACTS=crossings` | `0_prepare_osm_network` | builds only the crossings, not the 5.8 M cycleway lines |
| `CAMPAIGN_SYNC=0` | `maproulette_tasks` | reads `output/` as the weekly ts run left it; mirroring would overwrite that run's manifest |
| `CAMPAIGN_OUTPUT_DIR=<dir>` | `maproulette_tasks` | writes the tasks there instead of over the tracked file |
| `MAPILLARY_ACCESS_TOKEN`, `MAPROULETTE_API_KEY` | `maproulette_tasks` | credentials, instead of `../utils/config_mapillary_privat.json` |

Measured locally: the crossings extract takes 19 s and 0.5 GB RAM (plus the 4.8 GB download),
the task notebook 23 s and 1.4 GB. The worker image does not contain `osmium` yet.

`processed_osm_files/` in this folder holds the extracts of the 2025 rounds and is not in git;
the [marking twin](../pedestrian_crossing_marking_campaign/) still reads its own copy.
