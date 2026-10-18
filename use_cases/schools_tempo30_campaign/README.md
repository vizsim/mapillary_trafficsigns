# Tempo 30 near schools — traffic signs

**Last updated:** 2026-10-18

Finds 30 km/h signs (DE:274-30) detected by Mapillary within 450 m of a school or
kindergarten, where no road within 50 m carries a 30 in OpenStreetMap, and turns them into
tasks for MapRoulette. Built like the `maproulette_*` pipeline of the
[cycleway campaigns](../cycleway_complete_campaign/README.md) and the other campaigns.

| | |
| --- | --- |
| **Produces** | tasks for MapRoulette challenge 52985 |
| **Triggered by** | a human, when a new round is due |
| **Runs in** | the repo's uv env (`uv sync` in the repo root) |
| **Needs** | the `osmium` CLI, a Mapillary token |

The steps live in [`../campaign.py`](../campaign.py), shared with the other campaigns; what
is specific to this one — what counts as a mapped 30, the distances, the task text — in
[`../t30_campaign.py`](../t30_campaign.py). Tests are next to them in `../test_*.py`.

---

## Pipeline

```text
../0_prepare_osm_network.ipynb          ← shared with the other campaigns
    Geofabrik PBF → osmium tags-filter
    →  ../utils/processed_osm_files/processed_maxspeed_germany_<date>.parquet   (ways with a maxspeed tag)
    →  ../utils/processed_osm_files/processed_schools_germany_<date>.parquet    (schools, kindergartens)

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-t30_schools.geojson   (MapRoulette fetches it from GitHub)
```

> **Mind `set_date`.** It appears in both notebooks and has to match. Geofabrik keeps daily
> extracts for only about 90 days.

A new round: run the notebook, commit and push the GeoJSON, then "Rebuild tasks" in
MapRoulette. The file keeps its name, because the challenge's source URL points to it.
Uploading through the API instead is built in, but waits for MapRoulette — see the
[pedestrian-crossing README](../pedestrian_crossing_campaign/README.md#uploading-through-the-api).

## Selection

| Step | Setting |
| --- | --- |
| Sign | `regulatory--maximum-speed-limit-30--g1` (DE:274-30) |
| Last seen after | `2025-01-01` |
| First to last sighting | at least 12 months |
| Clipped to | the German border |
| No road within 50 m with a 30 | `maxspeed`, `:forward`, `:backward` or `:hgv` = `30`, a `:conditional` variant with `30 @`, or `zone:maxspeed=DE:30`, on the road types in `t30.STRASSENTYPEN` |
| School or kindergarten within | 450 m, as point or area (`t30.SCHULRADIUS_M`) |
| Signs that become one task | up to 30 m apart (`t30.ZUSAMMENFASSEN_M`); the one seen last stays |
| Existing tasks that block | all but Fixed, Created and Skipped, within 50 m |
| Names of closed tasks in the challenge | dropped |

The 450 m are what the 2025 round computed: it buffered the sign by 50 m and the school by
400 m. Its challenge description said 400 m.

On the Mapillary data of 14.10.2026 and the OSM extract of 17.10.2026 this gave 982 tasks.

## The 2025 round, and why this one replaces its open tasks

The tasks of the 2025 round were named after the **image**, not the detection — feature id
and `image_id` were swapped — and the image was `images[-1]`, the last element of an
unsorted list. Their 405 open tasks cannot be refreshed in place, so this round replaces
them: **"Rebuild tasks" with "remove unmatched"**. That deletes the open (Created) tasks and
creates the new ones; the challenge had no skipped tasks. Tasks marked as false positive or
already fixed stay and keep blocking their place.

## What changed from the 2025 round

On the same data — the OSM extract of 05.08.2025 and the signs of 14.10.2026 — the old
notebook and this one pick the same 1,448 signs, before the steps below. The differences:

- **Clipped to Germany**, as the other campaigns.
- **Signs up to 30 m apart become one task.** The old notebook computed this, but wrote the
  tasks without it.
- **Existing tasks are taken into account**; the old notebook did not look at the challenge.
- **Newest image** from the Graph API, and image and detection id in their right places.
- **OSM extracts** from the shared notebook: the roads with a maxspeed tag instead of every
  road (370 MB instead of 968 MB), schools with a count check against osmium.
- **Task text:** the same content; the conditional examples use `-` instead of `–`, which is
  not valid in a `maxspeed:conditional` value.
