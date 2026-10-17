# Cycleway campaign — traffic signs

**Last updated:** 2026-10-17

Two independent pipelines share this folder; the filename prefix says which is which.
The twin [`../cycleway_complete_marking_campaign/`](../cycleway_complete_marking_campaign/)
does the same for bicycle symbols painted on the road.

| | `maproulette_*` | `radinfra_*` |
| --- | --- | --- |
| **Produces** | tasks for MapRoulette challenge 52916 | GeoJSON and vector tiles for radinfra.de |
| **Triggered by** | a human, when a new round is due | cron on the server, **Wednesdays 15:00 UTC** |
| **Runs in** | the repo's uv env (`uv sync` in the repo root) | the worker image, built from the same [`uv.lock`](../../uv.lock) |
| **Needs** | the `osmium` CLI, a MapRoulette key, a Mapillary token | only `output/*.parquet` and the motorway file |

The logic of both lives in [`../cw_campaign.py`](../cw_campaign.py) (tested in
[`../test_cw_campaign.py`](../test_cw_campaign.py)); the notebooks only call it. Why a
function works the way it does is in its docstring.

---

## `maproulette_*` — tasks for mappers

Finds traffic signs that mandate cycling infrastructure where OpenStreetMap has none
nearby.

```text
../0_prepare_osm_network.ipynb          ← shared with the marking campaign
    Geofabrik PBF → osmium tags-filter
    →  ../utils/processed_osm_files/processed_cycleways_germany_<date>.parquet

maproulette_tasks.ipynb
    →  maproulette_tasks_missing-cw_instruction_vz_name_new.geojson
```

> **Mind `set_date`.** It appears in `0_prepare_osm_network.ipynb`, in
> `maproulette_tasks.ipynb` **and** in the marking campaign. Geofabrik keeps daily
> extracts for only about 90 days.

The output keeps its name on every run, because MapRoulette needs a stable path. The
last cell of the notebook, and `git diff`, show what changed.

---

## `radinfra_*` — data for radinfra.de

Publishes every cycling-related traffic sign. **Runs unattended in production.**

```text
scripts/run_worker_with_vpn_ts.sh
  └─ scripts/run_mapillary_notebooks.sh ts
       1. python3 -m mapillary_pipeline ts         (fetches the tiles)
       2. radinfra_1_export.ipynb   →  ts_output/*.geojson.gz, README.md, signs_by_month.svg
       3. radinfra_2_pmtiles.ipynb  →  ts_output/*.pmtiles
  └─ scripts/upload_outputs_to_b2.sh   →  data.vizsim.de
```

If a step fails, nothing is uploaded and data.vizsim.de keeps last week's state. The run
is logged in `logs/cron-ts.log`, the executed notebooks end up in
`logs/executed/ts_*.ipynb`. A single state can be fetched again with
`python3 -m mapillary_pipeline ts --bundesland DE-NW`.

---

## Before changing the code

- **Never renumber the row index.** It becomes the `id` of each feature in the GeoJSON
  and the vector tiles, and radinfra.de depends on it. Tests pin this.
- **`radinfra_1_export.ipynb` does not call `sync_features`.** On the server, step 1
  produces the parquets, so a sync would replace them with last week's copy from B2.

## Running it

```bash
# in the repo root
uv sync
uv run pytest          # all tests, no network, a few seconds
uv run jupyter lab     # the maproulette pipeline, by hand
```

Credentials come from `../utils/config_mapillary_privat.json`, or from the environment
variables `MAPILLARY_ACCESS_TOKEN` and `MAPROULETTE_API_KEY`.

Notebooks are committed without outputs. Set up the filter for that once per clone, as
described in [`.gitattributes`](../../.gitattributes).

`blogpost.md` is a write-up about the campaign. `ts_output/` and `processed_osm_files/`
(older OSM extracts) are not in git.
