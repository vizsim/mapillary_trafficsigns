# Cycleway campaign — traffic signs

**Last updated:** 2026-09-20

Two independent pipelines run in this folder. They share input data and, since
2026-09-20, code as well — but they are started by different people at different times
in different environments. The filename prefix tells you which is which:
`maproulette_*` or `radinfra_*`.

The twin of this campaign is
[`../cycleway_complete_marking_campaign/`](../cycleway_complete_marking_campaign/): same
structure, same notebook names, but it detects cycleways from road markings instead of
traffic signs.

---

## `maproulette_*` — tasks for mappers

Finds traffic signs that mandate cycling infrastructure where OpenStreetMap has none
nearby, and turns them into tasks for MapRoulette challenge 52916.

| | |
| --- | --- |
| **Triggered by** | a human, when a new round of the challenge is due |
| **Environment** | the uv env from [`use_cases/pyproject.toml`](../pyproject.toml) — run `uv sync` in `use_cases/` |
| **Also needs** | the `osmium` CLI, a MapRoulette API key, a Mapillary token |

```text
../0_prepare_osm_network.ipynb          ← shared with the marking campaign
    download Geofabrik PBF → osmium tags-filter → GeoParquet
    →  ../utils/processed_osm_files/processed_cycleways_germany_<date>.parquet  (~600 MB)

maproulette_tasks.ipynb
    intersect signs with OSM cycling infrastructure, fetch the newest Mapillary image
    →  maproulette_tasks_missing-cw_instruction_vz_name_new.geojson
```

> **Mind `set_date`.** The date appears in
> [`../0_prepare_osm_network.ipynb`](../0_prepare_osm_network.ipynb), in
> `maproulette_tasks.ipynb` **and** in the marking campaign, which reads the same file.
> Geofabrik only keeps daily extracts for about 90 days: once a PBF is gone both locally
> and upstream, that state of OSM cannot be rebuilt.

The output file keeps its name on every run, because MapRoulette needs a stable input
path. The notebook reads the previous contents *before* overwriting them, so the last
cell can tell you what changed. `git diff` on that file shows the same thing line by
line.

---

## `radinfra_*` — data for radinfra.de

Publishes every cycling-related traffic sign as GeoJSON and vector tiles.
**This runs unattended in production.**

| | |
| --- | --- |
| **Triggered by** | cron on the server, **Wednesdays 15:00 UTC** |
| **Environment** | the pip env inside the worker image, from [`requirements.txt`](../../requirements.txt), Python 3.12 |
| **Input** | only `output/*.parquet` and the static motorway file — no PBF, no osmium |

```text
scripts/run_worker_with_vpn_ts.sh
  └─ scripts/run_mapillary_notebooks.sh ts
       1. 2_get_mapillary_traffic_signs.ipynb     (repo root — fetches the tiles)
       2. radinfra_1_export.ipynb
             →  ts_output/mapillary_trafficsigns_bicycle_latest.geojson.gz
             →  ts_output/README.md, ts_output/signs_by_month.svg
       3. radinfra_2_pmtiles.ipynb
             →  ts_output/mapillary_trafficsigns_bicycle_latest.pmtiles
  └─ scripts/upload_outputs_to_b2.sh   →  data.vizsim.de
```

**If a notebook fails**, `run_worker_with_vpn.sh` exits with status 1 — **before** the B2
upload. Nothing half-finished is ever published; the previous state on data.vizsim.de
stays. The cost of a failure is one missed weekly update, not corrupted data.

**Where to look afterwards:**

| | |
| --- | --- |
| `logs/cron-ts.log` | the whole run, including one `▶️ <notebook>` line per step |
| `logs/ts_run_latest.log` | live transcript, but **only** of step 1 (the tile fetch) |
| `logs/executed/ts_*.ipynb` | the notebooks as nbconvert executed them — this is where the cell output of `radinfra_1_export` ends up |

There is no live transcript for steps 2 and 3: nbconvert only writes cell output once the
notebook finishes. While a step is running, `cron-ts.log` shows just the `▶️` line.

---

## Shared

| | |
| --- | --- |
| [`../cw_campaign.py`](../cw_campaign.py) | the logic behind both pipelines and both campaigns, 56 tests in [`../test_cw_campaign.py`](../test_cw_campaign.py) |
| `../utils/processed_osm_files/` | the cycleway network, built by [`../0_prepare_osm_network.ipynb`](../0_prepare_osm_network.ipynb), read by the marking campaign too |
| `../../output/mapillary_traffic-signs_DE-*.parquet` | detections per federal state |
| `../utils/processed_motorways_germany_251215.parquet` | motorways, rarely changes |
| `../utils/config_mapillary_privat.json` | Mapillary token and MapRoulette key |

`../cw_campaign.py` sits one level up because both cycleway campaigns use it. The
notebooks pick it up with `sys.path.insert(0, "..")`, which works because Jupyter and
nbconvert set the working directory to the notebook's own directory — the same
assumption `../../output/` and `../utils/` already rely on.

### The rule that is easy to miss

The module is imported **from two different environments**: the uv env for
`maproulette_*` and the worker image's pip env for `radinfra_*`.

> Every package `cw_campaign.py` imports must appear in **both** dependency lists, at the
> same version.

Otherwise `maproulette_*` keeps working while `radinfra_*` dies on a Wednesday night.
All shared packages currently match; `test_cw_campaign_laeuft_in_beiden_umgebungen`
pins that down.

That test is deliberately throwaway: once the repo moves to a single uv env (step 4 in
[`docs/plan_notebooks_zu_python.md`](../../docs/plan_notebooks_zu_python.md)), the
invariant holds structurally and the test can go.

---

## Why the code looks the way it does

Both notebooks were rewritten on 2026-09-20. These are the decisions worth knowing
before changing anything; the previous implementations (`1_…`, `x_…`) are still in the
folder for comparison.

### The row index is never renumbered

`GeoDataFrame.to_json()` writes it as the top-level `id` of each feature, tippecanoe
carries that into the vector tiles, and radinfra.de depends on it. So
`clip_to_boundary`, `filter_stable_signs` and `filter_by_days_seen` leave the index
alone, and `load_features` filters *while reading* each file rather than after
concatenating.

This is the kind of change no summary statistic reveals: during the rewrite one stray
`reset_index(drop=True)` shifted the ids of 158,652 out of 158,665 features while the
count, the columns, the first and the last Mapillary id all stayed identical. Pinned by
`test_clip_to_boundary_behaelt_den_index` and
`test_load_features_filtert_beim_lesen_und_praegt_den_index`.

### `radinfra_1_export.ipynb` does not call `sync_features`

On the server the parquet files are *produced* by step 1 of the same pipeline and only
then uploaded to B2, so the published copy always has a newer `Last-Modified` than the
local file. A sync would replace this week's fresh data with last week's. The
`maproulette_*` notebooks do sync — they run by hand on a machine that does not produce
the data itself.

### The linked photo is the newest one

The previous implementation took `images[-1]`, the last element of a list that is not
sorted by capture time. Measured across 600 signs in Bremen:

| | share |
| --- | ---: |
| `images[-1]` was not the newest image | 84 % |
| more than 30 days older than available | 21 % |
| more than a year older | 10 % |
| more than two years older | 4 % |
| 99th percentile of the gap | 2,511 days |

`newest_image_ids` asks the Graph API for `images{id,captured_at}` — field expansion that
is not in Mapillary's documentation — and takes the maximum. It also fetches up to 50
features per request: 1.9 s instead of 30.5 s for 200 features.

No trade-off against visibility, which was the obvious worry: the newest image is also
*closer* to the sign on average (median 19.8 m versus 28.3 m for the previously chosen
one).

**What remains:** for about 2 % of tasks even the newest image in the `images` edge
predates the parquet's `last_seen_at`, occasionally by years. For exactly those features
the API also fails to return its own `last_seen_at`. The image that timestamp rests on
simply is not in the edge; there is nothing better to pick.

### One distance column instead of two buffer passes

`1_` built two buffered copies of the dataset (25 m and 30 m), intersected both against
the cycleway network and merged them back with `concat` + `sort_values` +
`drop_duplicates`. That is a laborious way to write one distance classification: anything
without cycling infrastructure within 30 m has none within 25 m either.

`distance_to_nearest` measures once and `assign_priority` derives the MapRoulette
priority from thresholds in `PRIO_AB_DISTANZ`. The task texts name the measured distance
("about 27 m") instead of a threshold, and a third priority level is one line rather than
a third buffer pass.

It stays fast because the 5.8 M OSM lines are never reprojected: a buffer around the few
thousand points moves into the lines' CRS, and only the hits of that prefilter are
measured metrically. 25,726 signs against 822,745 ways: 4.9 s.

---

## Running it

```bash
cd use_cases

# tests (no network, ~2 s)
uv run pytest test_cw_campaign.py

# the maproulette pipeline, by hand
uv run jupyter lab
```

Credentials come from `../utils/config_mapillary_privat.json`, or from the environment
variables `MAPILLARY_ACCESS_TOKEN` and `MAPROULETTE_API_KEY` if those are set.

## What else lives here

| | |
| --- | --- |
| `blogpost.md` | write-up about the campaign |
| `1_merge_…ipynb`, `x_…ipynb` | the previous implementations, kept until the new ones have survived a few weekly runs; how they were verified against each other is in the git history |
| `processed_osm_files/` | older OSM extracts from before the shared `0_prepare`, not in git |
| `ts_output/` | output of the radinfra pipeline, not in git |
| `ts_output_ref/` | reference run used by the comparison cell, not in git |
