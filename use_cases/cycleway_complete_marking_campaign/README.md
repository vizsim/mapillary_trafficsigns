# Cycleway campaign — road markings

**Last updated:** 2026-10-17

The twin of [`../cycleway_complete_campaign/`](../cycleway_complete_campaign/): same two
pipelines, same notebook names, same shared module. The difference is what the
detections are: **bicycle symbols painted on the road**, not traffic signs.

| | `maproulette_*` | `radinfra_*` |
| --- | --- | --- |
| **Produces** | tasks for MapRoulette challenge 53882 | GeoJSON and vector tiles for radinfra.de |
| **Triggered by** | a human, when a new round is due | cron on the server, **Thursdays 01:00 UTC** |
| **Runs in** | the repo's uv env (`uv sync` in the repo root) | the worker image, built from the same [`uv.lock`](../../uv.lock) |
| **Needs** | the `osmium` CLI, a MapRoulette key, a Mapillary token | only `output/*.parquet` — no motorway filter |

Running it, credentials and the rules for changing the code are in the
[twin's README](../cycleway_complete_campaign/README.md#before-changing-the-code).

---

## `maproulette_*` — tasks for mappers

Finds bicycle symbols on the road where OpenStreetMap has no cycling infrastructure
nearby.

```text
../0_prepare_osm_network.ipynb          ← shared with the traffic-sign campaign
    →  ../utils/processed_osm_files/processed_cycleways_germany_<date>.parquet

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-cw_markings.geojson
```

> **Mind `set_date`.** Both campaigns read the same cycleway file, so the date in
> `maproulette_tasks.ipynb` has to match the one in
> [`../0_prepare_osm_network.ipynb`](../0_prepare_osm_network.ipynb).

---

## `radinfra_*` — data for radinfra.de

Publishes every detected bicycle symbol. **Runs unattended in production.**

```text
scripts/run_worker_with_vpn_mk.sh
  └─ scripts/run_mapillary_notebooks.sh mk
       1. python3 -m mapillary_pipeline mk         (fetches the tiles)
       2. radinfra_1_export.ipynb   →  mk_output/*.geojson.gz, README.md, markings_by_month.svg
       3. radinfra_2_pmtiles.ipynb  →  mk_output/*.pmtiles
  └─ scripts/upload_outputs_to_b2.sh   →  data.vizsim.de
```

If a step fails, nothing is uploaded and data.vizsim.de keeps last week's state. Logs are
in `logs/cron-mk.log` and `logs/executed/mk_*.ipynb`.

> **Watch the memory.** The mk worker is capped at 6.5 GB and a run peaked at 5.3 GB
> locally: the map-feature parquets carry every feature class, not just bicycle symbols.

---

## How this campaign differs from its twin

Both `maproulette_tasks.ipynb` call the same functions in
[`../cw_campaign.py`](../cw_campaign.py), with different settings:

| | traffic signs | markings |
| --- | --- | --- |
| Dataset | `PREFIX_ZEICHEN` | `PREFIX_MARKIERUNGEN` |
| Classes | 4 traffic signs | 1 marking (bicycle symbol) |
| Seen after | `2025-07-01` | `2025-01-01` |
| Counts as cycling infrastructure | `designated` | `designated`, **`yes`** |
| Motorway exclusion | yes | no |
| Task text | `aufgabe_verkehrszeichen` | `aufgabe_markierung` |

The `yes` is intentional: a painted bicycle symbol often sits on a way where cycling is
merely permitted, not mandated. It raises the number of OSM ways counted as cycling
infrastructure from about 0.8 M to 1.4 M.

The `radinfra_*` exports differ too: the markings are clipped to the German border and
need more than 180 days between first and last sighting; the traffic signs have no
minimum lifetime but drop everything near a motorway. Both grew that way and stay, so the
published series remain comparable.

`mk_output/` and `processed_osm_files/` (older OSM extracts) are not in git.
