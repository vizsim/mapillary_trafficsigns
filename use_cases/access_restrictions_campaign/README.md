# Access restrictions campaign — traffic signs

**Last updated:** 2026-10-18

Finds prohibition signs detected by Mapillary — DE:250, 251, 253, 254, 255, 259, 260 —
where no OSM way within 30 m carries a tag for the traffic the sign is about, and turns them
into tasks for MapRoulette. Built like the `maproulette_*` pipeline of the
[cycleway campaigns](../cycleway_complete_campaign/README.md) and the
[pedestrian-crossing campaign](../pedestrian_crossing_campaign/README.md).

| | |
| --- | --- |
| **Produces** | tasks for MapRoulette challenge 54768 |
| **Triggered by** | a human, when a new round is due |
| **Runs in** | the repo's uv env (`uv sync` in the repo root) |
| **Needs** | the `osmium` CLI, a Mapillary token |

The steps live in [`../campaign.py`](../campaign.py), shared with the other campaigns; what
is specific to this one — the signs, which OSM keys count for each, the task text — in
[`../ar_campaign.py`](../ar_campaign.py). Tests are next to them in `../test_*.py`.

---

## Pipeline

```text
../0_prepare_osm_network.ipynb          ← shared with the other campaigns
    Geofabrik PBF → osmium tags-filter w/access w/vehicle w/motor_vehicle ...
    →  ../utils/processed_osm_files/processed_access_restrictions_germany_<date>.parquet

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-access-restrictions.geojson   (MapRoulette fetches it from GitHub)
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
| Signs | `ar.ZEICHEN` — 250, 251, 253, 254, 255, 259, 260 |
| Last seen after | `2025-07-01` |
| First to last sighting | at least 9 months |
| Clipped to | the German border |
| No way within 30 m carrying | a key of the sign's group (`ar.SCHLUESSEL`), any value |
| Ways that count | every way with such a key, areas like parking lots included (`nur_strassen = False`) |
| Existing tasks that block | all but Fixed, Created and Skipped, within 30 m |
| Names of closed tasks in the challenge | dropped — MapRoulette would update that task in place, and it would stay closed; open tasks of the same name get refreshed |

Which keys count: a no-bicycles sign (254) is answered by `bicycle=*`, `vehicle=*` or
`access=*` on a way nearby, a no-pedestrians sign (259) by `foot=*` or `access=*`, and so on.
The value does not matter, so `bicycle=yes` next to a no-bicycles sign counts as mapped.

On the Mapillary data of 14.10.2026 and the OSM extract of 17.10.2026 this gave 3,199 tasks:
973 open ones of challenge 54768 refreshed, 2,226 new. Most are DE:253 (no heavy goods
vehicles) and DE:250 (no vehicles).

### Open question: do parking lots count?

The OSM extract holds every way with an access key, also areas. As in the 2026 round, they
count: a sign within 30 m of a parking lot tagged `access=private` is taken as mapped. With
`nur_strassen = True` only roads and paths count, which gave **1,054 candidates more** on the
data of 17.10.2026 (4,588 instead of 3,534). About four in five of the ways that made the
difference were `amenity=parking`, the rest mostly playgrounds, gardens and bicycle parkings.
A sign at the entrance of a private parking lot is answered by its `access=private`; a sign on
the road next to it is not.

## What changed from the 2026 round

On the same data and with the same ways, the old notebook and this one pick the same 3,534
signs. The differences:

- **Newest image** from the Graph API instead of `images[-1]`, the last element of an unsorted
  list.
- **Names of closed tasks are dropped**, see above.
- **OSM extract** from the shared notebook: only the eight keys the campaign compares, 541 MB
  instead of 2.3 GB. `maxweight` and its kin were extracted before but never used. The cosmo
  variant is gone.
- **Task text** laid out like the other campaigns, naming the keys that were looked for.

`processed_osm_files/` and `processed_mapillary_files/` in this folder hold the data of the
April round and are not in git.
