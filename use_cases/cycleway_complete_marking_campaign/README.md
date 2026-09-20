# Cycleway campaign — road markings

**Last updated:** 2026-09-20

Two independent pipelines run in this folder, exactly as in the twin campaign
[`../cycleway_complete_campaign/`](../cycleway_complete_campaign/). Same structure, same
notebook names, same shared module — the difference is what the detections are:
**bicycle symbols painted on the road**, not traffic signs.

The filename prefix tells you which pipeline a notebook belongs to: `maproulette_*` or
`radinfra_*`.

---

## `maproulette_*` — tasks for mappers

Finds bicycle symbols on the road where OpenStreetMap has no cycling infrastructure
nearby, and turns them into tasks for MapRoulette challenge 53882.

| | |
| --- | --- |
| **Triggered by** | a human, when a new round of the challenge is due |
| **Environment** | the uv env from [`use_cases/pyproject.toml`](../pyproject.toml) — run `uv sync` in `use_cases/` |
| **Also needs** | the `osmium` CLI, a MapRoulette API key, a Mapillary token |

```text
../0_prepare_osm_network.ipynb          ← shared with the traffic-sign campaign
    download Geofabrik PBF → osmium tags-filter → GeoParquet
    →  ../utils/processed_osm_files/processed_cycleways_germany_<date>.parquet  (~600 MB)

maproulette_tasks.ipynb
    intersect markings with OSM cycling infrastructure, fetch the newest Mapillary image
    →  maproulette_tasks_missing-cw_markings.geojson
```

> **Mind `set_date`.** Both campaigns read the same cycleway file, so the date in
> `maproulette_tasks.ipynb` has to match the one in
> [`../0_prepare_osm_network.ipynb`](../0_prepare_osm_network.ipynb). Until 2026-09-20
> this campaign quietly ran on an OSM extract from `260701` while the other one was on
> `260915`.

---

## `radinfra_*` — data for radinfra.de

Publishes every detected bicycle symbol as GeoJSON and vector tiles.
**This runs unattended in production.**

| | |
| --- | --- |
| **Triggered by** | cron on the server, **Thursdays 01:00 UTC** |
| **Environment** | the pip env inside the worker image, from [`requirements.txt`](../../requirements.txt), Python 3.12 |
| **Input** | only `output/*.parquet` — no PBF, no osmium, and no motorway filter |

```text
scripts/run_worker_with_vpn_mk.sh
  └─ scripts/run_mapillary_notebooks.sh mk
       1. 2b_get_mapillary_map_feature_points.ipynb   (repo root — fetches the tiles)
       2. radinfra_1_export.ipynb
             →  mk_output/mapillary_markings_bicycle_latest.geojson.gz
             →  mk_output/README.md, mk_output/markings_by_month.svg
       3. radinfra_2_pmtiles.ipynb
             →  mk_output/mapillary_markings_bicycle_latest.pmtiles
  └─ scripts/upload_outputs_to_b2.sh   →  data.vizsim.de
```

**If a notebook fails**, `run_worker_with_vpn.sh` exits with status 1 — **before** the B2
upload. Nothing half-finished is ever published; the previous state on data.vizsim.de
stays. The cost of a failure is one missed weekly update, not corrupted data.

**Where to look afterwards:**

| | |
| --- | --- |
| `logs/cron-mk.log` | the whole run, including one `▶️ <notebook>` line per step |
| `logs/mk_run_latest.log` | live transcript, but **only** of step 1 (the tile fetch) |
| `logs/executed/mk_*.ipynb` | the notebooks as nbconvert executed them |

> **Watch the memory.** The mk worker is capped at 6.5 GB and a run peaked at 5.3 GB
> locally — the map-feature-point parquets carry every feature class, not just bicycle
> symbols. That is 82 % of the limit, and the worker has died of memory pressure before.

---

## How this campaign differs from its twin

Both `maproulette_tasks.ipynb` notebooks call the same functions in
[`../cw_campaign.py`](../cw_campaign.py), just with different settings:

| | traffic signs | markings |
| --- | --- | --- |
| Dataset | `PREFIX_ZEICHEN` | `PREFIX_MARKIERUNGEN` |
| Classes | 4 traffic signs | 1 marking (bicycle symbol) |
| Seen after | `2025-07-01` | `2025-01-01` |
| Counts as cycling infrastructure | `designated` | `designated`, **`yes`** |
| Motorway exclusion | yes | no |
| MapRoulette challenge | 52916 | 53882 |
| Task text | `aufgabe_verkehrszeichen` | `aufgabe_markierung` |

That `yes` matters: it raises the number of OSM ways counted as cycling infrastructure
from 822,745 to **1,444,646**. Intentionally so — a painted bicycle symbol often sits on
a way where cycling is merely permitted, not mandated.

`aufgabe_markierung` highlights the symbol in Mapillary (`mapFeature[]=` instead of
`trafficSign[]=`), shows both layers in TILDA, and appends copy-paste templates for
advisory lanes, mandatory lanes and pictogram chains.

The `radinfra_*` pipelines differ more: this one clips to the German border and filters
on **days** between first and last sighting (180), while the traffic-sign one filters on
**months** and excludes motorways. Both grown that way, both kept, so the published
series stay comparable.

---

## Why the code looks the way it does

Both notebooks were rewritten on 2026-09-20. The shared decisions are documented in the
[twin campaign's README](../cycleway_complete_campaign/README.md#why-the-code-looks-the-way-it-does)
— the row index that must not be renumbered, the missing `sync_features` in the server
notebook, and why the linked photo is now the newest one. Everything below is specific
to this campaign.

### The challenge cleanup now actually applies

`1_` computed which candidates already exist as MapRoulette tasks (cell 47) and then
threw the result away (cell 50):

```python
df_process_img = df_buffered_both_false.copy()
#df_process_img = df_buffered_both_false_no_challenge.copy()    # the cleaned version
```

Places already marked *Not an issue* or *Already fixed* therefore reappeared as tasks in
the next round. In the current run that affects **41 of 634** candidates. The
traffic-sign campaign never had this bug.

### The published README carries a cosmetic artifact

`mk_output/README.md` reports the detection period as
`2014-03-30 00:00:00 - 2026-09-15 00:00:00`. The `00:00:00` is an artifact: the previous
implementation held the date columns as `datetime` at that point. `radinfra_1_export`
reproduces it on purpose so that its output stayed byte-identical to `x_` during the
switch. Dropping it is a one-line change in the notebook, worth doing once the old
notebook is gone.

### Days, not months

This campaign filters on **days** between first and last sighting (more than 180), the
traffic-sign one on **months** (at least 9). Both grew that way and both are kept, so the
published series stay comparable. `filter_by_days_seen` and `filter_stable_signs` exist
side by side for that reason.

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
| `1_merge_…ipynb`, `x_…ipynb` | the previous implementations, kept until the new ones have survived a few weekly runs; how they were verified against each other is in the git history |
| `processed_osm_files/` | older OSM extracts from before the shared `0_prepare`, not in git |
| `mk_output/` | output of the radinfra pipeline, not in git |
| `mk_output_ref/` | reference run used by the comparison cell, not in git |
