# Mapillary detection filters (age, repetition, context)

This document describes **why** we apply certain thresholds when turning raw Mapillary traffic-sign and marking detections into **mapper-facing** datasets (for example radinfra.de exports and MapRoulette tasks). The canonical numeric values live in one Python module so notebooks and docs stay aligned.

**Code:** [`use_cases/shared/detection_filter_constants.py`](../use_cases/shared/detection_filter_constants.py)

---

## User story: what the mapper should experience

1. **Still true on the street**
   Recency is driven by **`last_seen_at`**: we keep detections where the feature still appears in Mapillary imagery recently enough that a mapper opening a sequence can plausibly still see it. At export time, the minimum allowed `last_seen_at` is the **current local date in `Europe/Berlin`** minus [`LAST_SEEN_LOOKBACK_MONTHS`](../use_cases/shared/detection_filter_constants.py) calendar months. That lookback is configured as **36** months (**3** years). The computed cutoff is written to `freshness_metadata.json` next to each export README.

2. **Trust in bicycle *markings* is harder than trust in *signs***
   Pavement symbols are easy for models to confuse with paint wear, shadows, or unrelated graphics. For **markings** we require a **repeat-observation** rule: the same detection id must span a **minimum number of calendar days** between `first_seen_at` and `last_seen_at`, which favors sightings spread over time without counting raw image rows.

3. **Traffic signs: keep noise off motorways**
   For **signs**, same-calendar-day **first_seen_at** and **last_seen_at** pairs get a **Hinweis** (possible temporary signage). **Markings** additionally enforce a minimum span between first and last sighting. Signs within the **motorway** buffer are excluded to reduce false positives on Autobahnen.

4. **Tile download and campaign export**
   Notebooks that **download tiles** into `output/` persist Mapillary timestamps as delivered. **Export** notebooks (for example `x_*_generateOutput_2radinfra.ipynb`) apply the filters below to build mapper-facing layers.

---

## Rules summary

| Idea | Traffic signs (radinfra bicycle sign layer) | Bicycle pavement markings |
|------|-----------------------------------------------|---------------------------|
| Recency | `last_seen_at` \> rolling cutoff (Berlin, month lookback) | Same |
| “How often” / stability | Same-day first/last: **Hinweis** in export | Minimum calendar days between first and last sighting |
| Extra | Exclude within motorway buffer | Clip to Germany boundary |

### Constants and helpers (links to definitions)

| Name | Role |
|------|------|
| [`FRESHNESS_TIMEZONE`](../use_cases/shared/detection_filter_constants.py) | Time zone for “today” when computing the rolling `last_seen` cutoff (`Europe/Berlin`). |
| [`LAST_SEEN_LOOKBACK_MONTHS`](../use_cases/shared/detection_filter_constants.py) | Configured month lookback: **36** months (**3** years). |
| [`compute_last_seen_cutoff_date` / `compute_last_seen_cutoff_date_str`](../use_cases/shared/detection_filter_constants.py) | Cutoff date / ISO string used in filters. |
| [`freshness_export_metadata`](../use_cases/shared/detection_filter_constants.py) | Dict mirrored to `freshness_metadata.json` (config + computed cutoff + Berlin run timestamp). |
| [`FIRST_SEEN_VALID_AFTER_STR`](../use_cases/shared/detection_filter_constants.py) | Valid `first_seen_at` lower bound when loading markings (data hygiene). |
| [`MIN_DAYS_BETWEEN_FIRST_AND_LAST_OBSERVATION`](../use_cases/shared/detection_filter_constants.py) | **Markings only:** minimum span between first and last sighting. |
| [`MOTORWAY_EXCLUSION_BUFFER_M`](../use_cases/shared/detection_filter_constants.py) | **Traffic signs only:** buffer used to exclude motorway-adjacent points. |

---

## Where it is implemented

- **Traffic signs export (filters + motorway exclusion + single-day hint):**
  [`use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb`](../use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb)
  Generated README: [`use_cases/cycleway_complete_campaign/ts_output/README.md`](../use_cases/cycleway_complete_campaign/ts_output/README.md)
  Sidecar: `ts_output/freshness_metadata.json`

- **Markings export (recency + minimum day span + Germany):**
  [`use_cases/cycleway_complete_marking_campaign/x_mapillary-markings_generateOutput_2radinfra.ipynb`](../use_cases/cycleway_complete_marking_campaign/x_mapillary-markings_generateOutput_2radinfra.ipynb)
  Generated README: [`use_cases/cycleway_complete_marking_campaign/mk_output/README.md`](../use_cases/cycleway_complete_marking_campaign/mk_output/README.md)
  Sidecar: `mk_output/freshness_metadata.json`

- **Nationwide tile download:**
  [`2_get_mapillary_traffic_signs.ipynb`](../2_get_mapillary_traffic_signs.ipynb) — writes per–Bundesland extracts under `output/` with Mapillary fields as provided; campaign filters run in the export notebooks above.

---

## Attribution

Mapillary detection timestamps and geometry are subject to [Mapillary’s documentation](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE) and license terms used elsewhere in this repository.
