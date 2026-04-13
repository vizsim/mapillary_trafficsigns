# Mapillary detection filters (age, repetition, context)

This document describes **why** we apply certain thresholds when turning raw Mapillary traffic-sign and marking detections into **mapper-facing** datasets (for example radinfra.de exports and MapRoulette tasks). The canonical numeric values live in one Python module so notebooks and docs stay aligned.

**Code:** [`use_cases/shared/detection_filter_constants.py`](../use_cases/shared/detection_filter_constants.py)

---

## User story: what the mapper should experience

1. **Still true on the street**
   We only want points where the feature was still visible in Mapillary imagery **recently enough** that a mapper who opens a photo sequence is likely to see the same sign or marking. That is expressed as a cutoff on **`last_seen_at`** (not on the age of the first photo).

2. **Trust in bicycle *markings* is harder than trust in *signs***
   Pavement symbols are easy for models to confuse with paint wear, shadows, or unrelated graphics. So for **markings** we add a **repeat-observation** rule: the same detection id must have been seen over a **minimum span of calendar days** between `first_seen_at` and `last_seen_at`. That approximates “seen more than once / not a one-frame glitch,” without us having to count raw image rows.

3. **Traffic signs: keep noise off motorways**
   For **signs**, we do **not** apply the same minimum-day span as a hard filter. Instead we **flag** same-day-only detections in a hint field (possible temporary signage). We **exclude** signs near **motorways** with a fixed buffer, because many false positives cluster there.

4. **Raw download vs. campaign export**
   The notebooks that **download tiles** into `output/` store Mapillary’s timestamps as-is. The **filters below** apply in the **per–use-case export** notebooks (for example `x_*_generateOutput_2radinfra.ipynb`), not in the initial nationwide extract.

---

## Rules summary

| Idea | Traffic signs (radinfra bicycle sign layer) | Bicycle pavement markings |
|------|-----------------------------------------------|---------------------------|
| Recency | Keep if `last_seen_at` \> cutoff | Same |
| “How often” / stability | No minimum day-span filter; **hint** if only one day of sightings | **Require** `last_seen_at - first_seen_at` \> N days |
| Extra | Drop if within motorway buffer | Germany boundary clip |

### Constants (links to definitions)

| Constant | Role |
|----------|------|
| [`LAST_SEEN_CUTOFF_DATE_STR`](../use_cases/shared/detection_filter_constants.py) | Detection must still appear after this date (`last_seen_at`). |
| [`FIRST_SEEN_VALID_AFTER_STR`](../use_cases/shared/detection_filter_constants.py) | Valid `first_seen_at` lower bound when loading markings (data hygiene). |
| [`MIN_DAYS_BETWEEN_FIRST_AND_LAST_OBSERVATION`](../use_cases/shared/detection_filter_constants.py) | **Markings only:** minimum span between first and last sighting. |
| [`MOTORWAY_EXCLUSION_BUFFER_M`](../use_cases/shared/detection_filter_constants.py) | **Traffic signs only:** buffer used to exclude motorway-adjacent points. |

---

## Where it is implemented

- **Traffic signs export (filters + motorway exclusion + single-day hint):**
  [`use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb`](../use_cases/cycleway_complete_campaign/x_mapillary-trafficsigns_generateOutput_2radinfra.ipynb)
  Generated README: [`use_cases/cycleway_complete_campaign/ts_output/README.md`](../use_cases/cycleway_complete_campaign/ts_output/README.md)

- **Markings export (recency + minimum day span + Germany):**
  [`use_cases/cycleway_complete_marking_campaign/x_mapillary-markings_generateOutput_2radinfra.ipynb`](../use_cases/cycleway_complete_marking_campaign/x_mapillary-markings_generateOutput_2radinfra.ipynb)
  Generated README: [`use_cases/cycleway_complete_marking_campaign/mk_output/README.md`](../use_cases/cycleway_complete_marking_campaign/mk_output/README.md)

- **Nationwide tile download (no campaign filters):**
  [`2_get_mapillary_traffic_signs.ipynb`](../2_get_mapillary_traffic_signs.ipynb)

---

## Attribution

Mapillary detection timestamps and geometry are subject to [Mapillary’s documentation](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE) and license terms used elsewhere in this repository.
