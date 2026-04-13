
# Bicycle Marking Detections Output

This folder contains the output file for detected bicycle markings from Mapillary.
The output has been created on **2026-04-08**.

## Overview

- **Total detections**: 28354
- **Mapillary dataset from**: 2026-04-08
- **Detection period**: 2014-03-30 00:00:00 - 2026-04-04 00:00:00
- **Marking type**: Lane marking - symbol (bicycle)

## Applied Filters

- Only detections with **2+ observations** (min. **180** days between first and last sighting)
- Only detections with **last_seen_at** after the rolling cutoff (Berlin local date minus the configured **36**‑month / **3**‑year lookback; **example** cutoff from `freshness_metadata.json`: **2023-04-13**)
- Restricted to **Germany** boundaries — rationale: [detection filters doc](../../../docs/mapillary-detection-filters.md)

**Constants in code:** [`use_cases/shared/detection_filter_constants.py`](../../shared/detection_filter_constants.py) (`LAST_SEEN_LOOKBACK_MONTHS`, `FRESHNESS_TIMEZONE`, `compute_last_seen_cutoff_date_str`, `freshness_export_metadata`, `MIN_DAYS_BETWEEN_FIRST_AND_LAST_OBSERVATION`, `FIRST_SEEN_VALID_AFTER_STR`).

**Per-run mirror:** [`freshness_metadata.json`](freshness_metadata.json).

## Output Files

- `mapillary_markings_bicycle_latest.geojson.gz` - Compressed GeoJSON with all markings
- `markings_by_month.svg` - Detection frequency over time
- `freshness_metadata.json` - Rolling `last_seen` cutoff and export timestamp (Berlin)

## Statistics Plot

![Anzahl pro Monat](markings_by_month.svg)
