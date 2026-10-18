# Pedestrian crossing campaign — traffic signs

**Last updated:** 2026-10-18

Finds pedestrian-crossing signs (DE:350) detected by Mapillary where OpenStreetMap has no
`highway=crossing` within 50 m, and turns them into tasks for MapRoulette. Built like the
`maproulette_*` pipeline of the [cycleway campaigns](../cycleway_complete_campaign/README.md).
Uploading the tasks through MapRoulette's API is built in, but MapRoulette does not accept it
yet — see [below](#uploading-through-the-api). There is no weekly export here.

| | |
| --- | --- |
| **Produces** | tasks for MapRoulette challenge 53589 |
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
    →  maproulette_tasks_missing-ped-crossing.geojson   (MapRoulette fetches it from GitHub)
    →  MapRoulette challenge 53589                      (API upload, CAMPAIGN_UPLOAD=1 - not yet)
```

> **Mind `set_date`.** It appears in both notebooks and has to match. Geofabrik keeps daily
> extracts for only about 90 days.

For now a new round goes as in the cycleway campaigns: run the notebook, commit and push the
GeoJSON, then "Rebuild tasks" in MapRoulette, which fetches the file from GitHub. The file keeps
its name, because the challenge's source URL points to it.

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
| Names of closed tasks in the challenge | dropped — MapRoulette would update that task in place, and it would stay closed; open tasks of the same name get refreshed |

On the Mapillary data of 14.10.2026 and the OSM extract of 17.10.2026, this gave 183 tasks.

## Uploading through the API

`campaign.upload_tasks` adds the new tasks to the challenge and leaves the existing ones as they
are, open ones included — no commit, no push, no "Rebuild tasks". MapRoulette answers with success
even when the import fails inside, so the function checks the challenge afterwards and raises if
a task is missing. The notebook calls it only with `CAMPAIGN_UPLOAD=1`.

It does not work yet: since maproulette-backend v4.11.0 (October 2026) MapRoulette refuses API
keys, and their announced replacement, personal access tokens, does not exist yet
([maproulette-backend#1288](https://github.com/maproulette/maproulette-backend/issues/1288)).
Once it does, only the header in `upload_tasks` changes. Hosting the file somewhere else than
GitHub is no way around it: the web UI locks a challenge's source URL as soon as the challenge
has tasks.

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

Both notebooks run unchanged under `jupyter nbconvert --execute` and take their settings from
the environment, so a run on the server needs no edit to them. The task notebook still writes
the tracked GeoJSON, though, and the deploy step stops updating a server with local changes —
so running it there only makes sense once the upload works.

| Variable | Notebook | Effect |
| --- | --- | --- |
| `OSM_EXTRACTS=crossings` | `0_prepare_osm_network` | builds only the crossings, not the 5.8 M cycleway lines |
| `CAMPAIGN_SYNC=0` | `maproulette_tasks` | reads `output/` as the weekly ts run left it; mirroring would overwrite that run's manifest |
| `CAMPAIGN_UPLOAD=1` | `maproulette_tasks` | uploads the tasks to the challenge (not yet, see above); without it, the notebook only says how many it would upload |
| `MAPILLARY_ACCESS_TOKEN`, `MAPROULETTE_API_KEY` | `maproulette_tasks` | credentials, instead of `../utils/config_mapillary_privat.json`; the MapRoulette key must belong to an admin of the challenge |

Measured locally: the crossings extract takes 19 s and 0.5 GB RAM (plus the 4.8 GB download),
the task notebook 23 s and 1.4 GB. The worker image does not contain `osmium` yet.

The [marking twin](../pedestrian_crossing_marking_campaign/README.md) runs the same check on
zebra markings and shares `pc_campaign.py`. `processed_osm_files/` in this folder holds the
extracts of the 2025 rounds and is not in git.
